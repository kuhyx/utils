"""Run the contract check over every git repo under ~/src and ~ and write SWEEP.md."""

from __future__ import annotations

import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - plain-script import path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from repo_contract.check import Unreadable, violations

OUT = Path.home() / "data" / "claude-scratch" / "repo-contract" / "SWEEP.md"


@dataclass(frozen=True)
class Result:
    """Outcome for one repo."""

    name: str
    path: Path
    stacks: list[str]
    problems: list[str]
    error: str | None = None

    @property
    def passed(self) -> bool:
        """True when there were no problems and no read error."""
        return not self.problems and self.error is None


def find_repos(roots: list[Path]) -> list[Path]:
    """Direct children of each root that are git repos (`.git` is a directory)."""
    found = [
        d
        for r in roots
        if r.is_dir()
        for d in sorted(r.iterdir())
        if not d.name.startswith(".") and (d / ".git").is_dir()
    ]
    return sorted(found, key=lambda p: str(p))


def run_one(repo: Path) -> Result:
    """Check one repo, folding read errors into the result."""
    try:
        problems, stacks = violations(repo)
    except Unreadable as exc:
        return Result(repo.name, repo, [], [], f"unreadable: {exc}")
    return Result(repo.name, repo, stacks, problems)


def render(results: list[Result]) -> str:
    """Markdown report: summary, by-stack counts, per-repo table."""
    passed = sum(r.passed for r in results)
    by_stack: Counter[str] = Counter()
    fails: Counter[str] = Counter()
    for r in results:
        key = r.stacks[0] if r.stacks else "none"
        by_stack[key] += 1
        fails[key] += not r.passed
    out = [
        "# Repo contract sweep",
        "",
        f"{len(results)} repos: {passed} pass, {len(results) - passed} fail.",
        "",
        "| primary stack | repos | fail |",
        "|---|---|---|",
        *[f"| {s} | {n} | {fails[s]} |" for s, n in sorted(by_stack.items())],
        "",
        "| repo | result | stacks | missing |",
        "|---|---|---|---|",
    ]
    for r in results:
        verdict = "PASS" if r.passed else "FAIL"
        detail = r.error or "; ".join(r.problems)
        out.append(
            f"| {r.name} | {verdict} | {', '.join(r.stacks) or '-'} | {detail.replace('|', '/')} |"
        )
    return "\n".join(out) + "\n"


def main(
    argv: list[str] | None = None, roots: list[Path] | None = None, out: Path = OUT
) -> int:
    """Sweep, write the report, print the summary line. Always exit 0."""
    del argv
    home = Path.home()
    results = [run_one(r) for r in find_repos(roots or [home / "src", home])]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(results), encoding="utf-8")
    passed = sum(r.passed for r in results)
    print(
        f"repo-contract sweep: {len(results)} repos, {passed} pass, {len(results) - passed} fail -> {out}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
