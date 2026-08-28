"""Gate: fail when any dependency is behind its ecosystem's latest stable.

Exit codes are the adjudication — no judgement call, no model in the loop:

  0  everything current, or only validly-allowlisted staleness
  1  a dependency is behind latest stable / unpinned / lock-mismatched
  2  the allowlist is malformed, expired, over the 90-day cap, or stale
  3  cannot determine: no network and no usable cache

CI runs `--all --strict` and treats 1/2/3 as failure. Pre-commit runs without
`--strict`, where exit 3 degrades to 0 with a loud banner: `--no-verify` is
banned here, so a hook that hard-fails offline would leave no way to commit.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

from dep_freshness import report
from dep_freshness._tables import NPM
from dep_freshness.allowlist import AllowlistError, load, shared_path
from dep_freshness.discover import find_manifests, is_manifest, parse_manifest
from dep_freshness.evaluate import judge
from dep_freshness.models import Finding, Severity
from dep_freshness.quarantine import installable_latest
from dep_freshness.registries import http
from dep_freshness.resolve import Answer, Resolver


def repo_root(start: Path) -> Path:
    try:
        result = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=False,
        )
    except OSError:
        return start
    if result.returncode != 0:
        return start
    return Path(result.stdout.strip() or start)


def _excuse(
    findings: list[Finding], entries, shared: Path | None = None,
    whole_repo: bool = True,
) -> tuple[list[Finding], list]:
    """Split findings into (still failing, excused), and flag dead entries.

    A `transitive:` entry clears itself the moment its dependency is no longer
    stale — that is what makes it a predicate rather than a date. An entry with
    nothing left to excuse is allowlist rot and exits 2.

    Inherited entries are exempt from that rot check everywhere except the
    repo that owns the shared file. A fleet-wide hold on `typescript`
    legitimately excuses nothing in a Flutter app, and failing there would
    make every repo without that dependency uncommittable.

    `whole_repo` is False for a file-scoped run -- what pre-commit does, since
    it passes only the staged manifests. Such a run has seen a SUBSET of the
    repo by construction, so "no finding mentioned this package" carries no
    information about whether the entry is still needed. Judging rot there
    fails the commit over a manifest the commit never touched: staging two
    pubspec.yaml files in utils reported the fleet-wide typescript hold as
    dead, because no package.json was in scope to be found stale.
    """
    by_label = {f"{e.ecosystem}:{e.package}": e for e in entries}
    used: set[str] = set()
    failing: list[Finding] = []
    excused: list[Finding] = []
    for finding in findings:
        entry = by_label.get(finding.label)
        if entry is None:
            failing.append(finding)
            continue
        used.add(finding.label)
        excused.append(Finding(
            finding.dep, finding.severity, finding.latest, finding.detail,
            excused=entry.reason,
        ))
    dead = [
        e for e in entries
        if whole_repo
        and f"{e.ecosystem}:{e.package}" not in used
        and (shared is None or e.source != shared)
    ]
    return failing, dead


def _unquarantine(finding: Finding) -> Finding | None:
    """Re-judge an npm finding against what pnpm will actually install.

    pnpm 11 refuses a package published inside its quarantine window, so a
    repo pinned to the newest *installable* version is not behind in any sense
    a commit could fix. Only npm findings reach here, and only after a finding
    already exists, so the expensive full-document fetch never happens on a
    clean run.
    """
    if finding.dep.ecosystem != NPM or finding.latest is None:
        return finding
    installable = installable_latest(finding.dep.name, finding.latest)
    if installable is None or installable == finding.latest:
        return finding
    return judge(finding.dep, Answer(installable))


def collect(targets: list[Path], resolver: Resolver) -> list[Finding]:
    deps = [dep for path in targets for dep in parse_manifest(path)]
    resolver.prefetch(deps)
    findings = []
    for dep in deps:
        finding = judge(dep, resolver.latest(dep))
        if finding is None:
            continue
        finding = _unquarantine(finding)
        if finding is not None:
            findings.append(finding)
    return findings


def _targets(args, root: Path) -> list[Path]:
    if args.all:
        return find_manifests(root)
    return [p for p in args.paths if p.is_file() and is_manifest(p)]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fail if any dependency is behind latest stable."
    )
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--all", action="store_true",
                        help="check every manifest in the repo")
    parser.add_argument("--strict", action="store_true",
                        help="CI mode: an undeterminable answer is a failure")
    parser.add_argument("--refresh", action="store_true",
                        help="ignore the cache and re-fetch every version")
    parser.add_argument("--offline", action="store_true",
                        help="never touch the network; cache only")
    parser.add_argument("--exceptions-only", action="store_true",
                        help="report the allowlist and nothing else")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.all and not args.paths and not args.exceptions_only:
        build_parser().error("give manifest paths, --all, or --exceptions-only")

    root = repo_root(Path.cwd())
    if args.offline:
        http.force_offline(True)

    try:
        entries = load(root)
    except AllowlistError as exc:
        print(f"Allowlist ERROR: {exc}", file=sys.stderr)
        return 2

    if args.exceptions_only:
        if args.json:
            print(report.as_json([], entries, 0))
        else:
            for line in report.machine_lines(entries):
                print(line, file=sys.stderr)
        return 0

    resolver = Resolver(refresh=args.refresh)
    findings = collect(_targets(args, root), resolver)
    shared = shared_path()
    failing, dead = _excuse(
        findings, entries,
        shared=None if root == shared.parent else shared,
        whole_repo=args.all,
    )

    still_blocking = {f.label: True for f in findings}
    report.exceptions_block(entries, still_blocking)

    unknown = [f for f in failing if f.severity is Severity.UNKNOWN]
    real = [f for f in failing if f.severity is not Severity.UNKNOWN]

    if dead:
        for entry in dead:
            print(
                f"Allowlist ERROR: {entry.ecosystem}:{entry.package} is no longer "
                f"stale — remove the entry from {entry.source}",
                file=sys.stderr,
            )
        return 2

    if args.json:
        code = 1 if real else (3 if unknown and args.strict else 0)
        print(report.as_json(failing, entries, code))
        return code

    if real:
        report.violations(real, root)
        return 1
    if unknown or resolver.degraded:
        report.degraded(resolver.degraded or [f.label for f in unknown])
        return 3 if args.strict else 0
    return 0
