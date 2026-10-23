"""Bring every repo's repo-contract hook `files:` line up to the template.

Usage: python3 -m repo_contract.hook_sync [--apply] [REPO ...]
(default REPOs: the sweep roots, git repos directly under ~/src and ~).

Why this exists: `install.py` only checks that the hook id is present
(`precommit.needs_hook`), so widening the template's `files:` regex (as for
the Flutter launcher rules, 2026-10-23) never reaches a repo installed
earlier. This rewrites that one line with `precommit.set_hook_line` and leaves
the rest of the config, comments included, untouched.

Dry run by default: exit 1 when any repo is stale, 0 when all are current.
With --apply, stale repos are rewritten (not committed) and it exits 0.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - plain-script import path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from repo_contract.bootstrap import TEMPLATES
from repo_contract.precommit import hook_line, needs_hook, set_hook_line
from repo_contract.sweep import find_repos

HOOK_ID = "repo-contract"
SNIPPET = TEMPLATES / "pre-commit-snippet.yaml"
KEY = "files"


def template_line() -> str:
    """The template's `files:` line, exactly as a hook block carries it."""
    lines = SNIPPET.read_text(encoding="utf-8").splitlines()
    return next(ln for ln in lines if ln.startswith(f"        {KEY}:"))


def status(repo: Path) -> str:
    """`no hook`, `current` or `stale` for one repo."""
    if needs_hook(repo, HOOK_ID):
        return "no hook"
    current = hook_line(repo, HOOK_ID, KEY) == template_line()
    return "current" if current else "stale"


def main(argv: list[str] | None = None, roots: list[Path] | None = None) -> int:
    """CLI entry point; see the module docstring for exit codes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repos", nargs="*", type=Path)
    parser.add_argument("--apply", action="store_true", help="rewrite stale hooks")
    args = parser.parse_args(argv)
    home = Path.home()
    repos = args.repos or find_repos(roots or [home / "src", home])
    counts: Counter[str] = Counter()
    for repo in repos:
        state = status(repo)
        if state == "stale" and args.apply:
            set_hook_line(repo, HOOK_ID, KEY, template_line())
            state = "updated"
        counts[state] += 1
        label = "would update" if state == "stale" else state
        print(f"{label}: {repo}")
    print(
        f"hook-sync: {counts['stale']} stale, {counts['updated']} updated,"
        f" {counts['current']} current, {counts['no hook']} without the hook"
    )
    return 1 if counts["stale"] else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
