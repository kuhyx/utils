"""Install the repo-contract gate into a repo and bootstrap its Commands section.

Usage: python3 -m repo_contract.install REPO [--check] [--no-bootstrap]
(or `scripts/install_repo_contract_gate.sh REPO`).

Why this exists: the gate used to be four manual steps in the README. Nothing
ran them for a repo created after the 2026-10-04 rollout (teatr-pw and
teatr-pw-pytania were made ad hoc on 2026-10-09 and came out with no
`## Commands`, no shim, no hook), so the sweep was the first thing to notice.
One idempotent command now does all of it: delegate shim, pre-commit hook,
CI workflow (unless the repo opted out of GitHub Actions) and the Commands
section plus `scripts/test_changed.sh` through bootstrap.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - plain-script import path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dep_freshness.install import NO_WORKFLOW_MARKER
from repo_contract import bootstrap
from repo_contract.check import violations
from repo_contract.infer import propose
from repo_contract.stacks import detect_stacks

TEMPLATES = bootstrap.TEMPLATES
SHIM = Path("scripts/check_repo_contract.sh")
WORKFLOW = Path(".github/workflows/repo-contract.yml")
PRECOMMIT = Path(".pre-commit-config.yaml")
HOOK_ID = "repo-contract"
LOCAL_REPO = "  - repo: local"
EMPTY_PRECOMMIT = f"repos:\n{LOCAL_REPO}\n    hooks:\n"


def _template(name: str) -> str:
    return (TEMPLATES / name).read_text(encoding="utf-8")


def _needs_shim(repo: Path) -> bool:
    """False for utils itself, where SHIM is the real checker, not a delegate."""
    if (repo / "repo_contract" / "check.py").is_file():
        return False
    target = repo / SHIM
    return not target.is_file() or target.read_text(encoding="utf-8") != _template(
        "check_repo_contract.shim.sh"
    )


def _needs_workflow(repo: Path) -> bool:
    """Missing or drifted CI workflow, unless the repo opted out of Actions."""
    if (repo / NO_WORKFLOW_MARKER).exists():
        return False
    target = repo / WORKFLOW
    return not target.is_file() or target.read_text(encoding="utf-8") != _template(
        "repo-contract.yml"
    )


def _needs_hook(repo: Path) -> bool:
    target = repo / PRECOMMIT
    return not target.is_file() or f"id: {HOOK_ID}" not in target.read_text(
        encoding="utf-8"
    )


def _local_block_end(lines: list[str]) -> int:
    """Index just past the LAST `- repo: local` block, or -1 if there is none."""
    starts = [n for n, line in enumerate(lines) if line.rstrip() == LOCAL_REPO]
    if not starts:
        return -1
    after = [
        n for n in range(starts[-1] + 1, len(lines)) if lines[n].startswith("  - repo:")
    ]
    return after[0] if after else len(lines)


def _write_hook(repo: Path) -> None:
    """Insert the hook into the LAST local hooks list, keeping comments intact."""
    target = repo / PRECOMMIT
    body = target.read_text(encoding="utf-8") if target.is_file() else EMPTY_PRECOMMIT
    lines = (body if body.endswith("\n") else body + "\n").split("\n")[:-1]
    cut = _local_block_end(lines)
    if cut < 0:
        raise ValueError(
            f"{target} has no `{LOCAL_REPO}` block to add the hook to; "
            "add one by hand, then re-run"
        )
    block = [
        ln
        for ln in _template("pre-commit-snippet.yaml").rstrip("\n").split("\n")
        if not ln.startswith("#")
    ]
    lines[cut:cut] = ["", *block]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def plan(repo: Path) -> list[str]:
    """Which gate pieces are missing or drifted (the Commands section excluded)."""
    todo = []
    if _needs_shim(repo):
        todo.append(str(SHIM))
    if _needs_workflow(repo):
        todo.append(str(WORKFLOW))
    if _needs_hook(repo):
        todo.append(f"{PRECOMMIT} ({HOOK_ID} hook)")
    return todo


def install(repo: Path) -> list[str]:
    """Write every missing or drifted gate piece. Returns what changed."""
    done = []
    if _needs_shim(repo):
        target = repo / SHIM
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_template("check_repo_contract.shim.sh"), encoding="utf-8")
        target.chmod(0o755)
        done.append(str(SHIM))
    if _needs_workflow(repo):
        target = repo / WORKFLOW
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_template("repo-contract.yml"), encoding="utf-8")
        done.append(str(WORKFLOW))
    if _needs_hook(repo):
        _write_hook(repo)
        done.append(f"{PRECOMMIT} ({HOOK_ID} hook)")
    return done


def bootstrap_commands(repo: Path) -> list[str]:
    """Write the missing Commands lines and test_changed.sh (never overwrites)."""
    prop = propose(repo, detect_stacks(repo))
    doc = bootstrap.doc_path(repo)
    text = doc.read_text(encoding="utf-8") if doc.is_file() else ""
    new = bootstrap.missing_lines(prop, text)
    return bootstrap.apply(repo, doc, text, new, bootstrap.script_plan(repo, prop))


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; 0 contract satisfied, 1 violations left, 2 not a git repo."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("--check", action="store_true", help="report, change nothing")
    parser.add_argument("--no-bootstrap", action="store_true", help="gate pieces only")
    args = parser.parse_args(argv)
    repo = args.repo.expanduser().resolve()
    if not (repo / ".git").exists():
        print(f"install: {repo} is not a git repo", file=sys.stderr)
        return 2
    if args.check:
        for piece in plan(repo):
            print(f"would write: {piece}")
    else:
        for piece in install(repo):
            print(f"wrote: {piece}")
        if not args.no_bootstrap:
            for action in bootstrap_commands(repo):
                print(f"bootstrap: {action}")
    found, _ = violations(repo)
    for problem in found:
        print(f"repo-contract: {repo.name}: {problem}", file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
