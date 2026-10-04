"""Gate: the repo documents exact run/test/lint/coverage commands.

Usage: check.py [--repo PATH]. Exit 0 pass, 1 violations (printed), 2 not a
repo or unreadable CLAUDE.md. Contract text lives in README.md / DOCS-*.md.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - plain-script import path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from repo_contract.contract import (
    KEYS,
    LISTER,
    Entry,
    entry_problems,
    has_section,
    parse_entries,
    script_token,
    verbose_in_script,
)
from repo_contract.stacks import detect_stacks, has_tests

EXIT_OK, EXIT_VIOLATIONS, EXIT_UNREADABLE = 0, 1, 2
DOC_NAMES = ("CLAUDE.md", "AGENTS.md")


class Unreadable(Exception):
    """Raised for a path that is not a repo or a doc that cannot be read."""


def read_doc(repo: Path) -> str | None:
    """CLAUDE.md text (symlinks followed); None if absent; Unreadable on I/O error."""
    doc = repo / "CLAUDE.md"
    if not doc.exists():
        return None
    try:
        return doc.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise Unreadable(f"{doc}: {exc}") from exc


def _missing_doc(repo: Path) -> list[str]:
    """Violation for a missing CLAUDE.md, hinting at the AGENTS.md symlink."""
    if (repo / "CLAUDE.md").is_symlink():
        return ["CLAUDE.md is a dangling symlink"]
    if (repo / "AGENTS.md").is_file():
        return [
            "CLAUDE.md missing: symlink it to AGENTS.md (ln -s AGENTS.md CLAUDE.md)"
        ]
    return ["CLAUDE.md missing (or AGENTS.md that CLAUDE.md symlinks to)"]


def _check_changed(repo: Path, command: str) -> list[str]:
    """test-changed must run an existing, quiet entry-point script."""
    script = script_token(command, repo)
    if script is None:
        msg = "'- test-changed:' must invoke an existing changed-files script"
        return [f"{msg} (e.g. scripts/test_changed.sh)"]
    out: list[str] = []
    if not os.access(script, os.X_OK):
        out.append(f"{script.relative_to(repo)} is not executable")
    try:
        if verbose_in_script(script.read_text(encoding="utf-8")):
            out.append(f"{script.relative_to(repo)} runs a test tool verbosely")
    except (OSError, UnicodeDecodeError) as exc:
        raise Unreadable(f"{script}: {exc}") from exc
    return out


def _check_consistency(
    repo: Path, entries: dict[str, Entry], stacks: list[str]
) -> list[str]:
    """Cross-entry rules: n/a vs real tests, coverage-gaps lister."""
    out: list[str] = []
    test = entries["test"]
    if test.command is None:
        if has_tests(repo, stacks):
            out.append("'- test:' is n/a but the repo contains tests")
        for key in ("test-changed", "coverage", "coverage-gaps"):
            if entries[key].command is not None:
                out.append(f"'- {key}:' must be n/a when test is n/a")
        return out
    if entries["test-changed"].command is None:
        out.append("'- test-changed:' cannot be n/a while test is a real command")
    cov, gaps = entries["coverage"], entries["coverage-gaps"]
    if cov.command is not None and gaps.command is None:
        out.append(
            "'- coverage-gaps:' must run the shared lister: `coverage-gaps <report>`"
        )
    if gaps.command is not None and gaps.command.split()[0] != LISTER:
        out.append(f"'- coverage-gaps:' must start with `{LISTER} <report>`")
    return out


def violations(repo: Path) -> tuple[list[str], list[str]]:
    """(violations, detected stacks) for `repo`. Raises Unreadable."""
    stacks = detect_stacks(repo)
    text = read_doc(repo)
    if text is None:
        return _missing_doc(repo), stacks
    if not has_section(text):
        return ["CLAUDE.md has no '## Commands' section"], stacks
    entries, out = parse_entries(text)
    absent = [k for k in KEYS if k not in entries]
    if absent:
        out.append("'## Commands' is missing: " + ", ".join(f"- {k}:" for k in absent))
        return out, stacks
    for entry in entries.values():
        out.extend(entry_problems(entry))
    changed = entries["test-changed"]
    if changed.command is not None:
        out.extend(_check_changed(repo, changed.command))
    out.extend(_check_consistency(repo, entries, stacks))
    return out, stacks


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; returns the process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    repo = parser.parse_args(argv).repo.expanduser().resolve()
    if not repo.is_dir() or not (repo / ".git").exists():
        print(f"repo-contract: {repo} is not a git repo", file=sys.stderr)
        return EXIT_UNREADABLE
    try:
        found, _ = violations(repo)
    except Unreadable as exc:
        print(f"repo-contract: unreadable: {exc}", file=sys.stderr)
        return EXIT_UNREADABLE
    for problem in found:
        print(f"repo-contract: {repo.name}: {problem}", file=sys.stderr)
    return EXIT_VIOLATIONS if found else EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
