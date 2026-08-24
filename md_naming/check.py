"""Gate: fail if any markdown file breaks the naming convention.

Invoked by `scripts/check_md_naming.sh`, which pre-commit calls with the
staged files. Exits 1 and lists every violation; exits 0 silently otherwise.

Three rules, checked together because they only work as a set:

1. Naming    -- a markdown file must be README / CLAUDE* / DOCS* / TODO*.
2. Marker    -- a TODO* file must contain the removal marker.
3. Reverse   -- a file containing the marker must be named TODO*.

Rule 3 is what stops the convention leaking: without it a task file can be
renamed DOCS-something.md, keep its marker, and quietly become permanent.

The check is deliberately deterministic code rather than a judgement call --
adjudication belongs in an exit code, not in a model.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - plain-script import path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from file_length.check import git_ignored, iter_all
from md_naming.config import (
    MARKER,
    contains_marker,
    has_allowed_name,
    is_exempt,
    is_markdown,
    is_todo,
)


def absolutize(path: Path) -> Path:
    """`path` anchored at the cwd, without resolving symlinks.

    The exemption rules are written against full paths ('/.github/'), but
    pre-commit passes paths relative to the repo root ('docs/x.md') while
    --all walks absolute ones. Matching a relative path against those rules
    silently drops the repo-name context, so the same file would pass the
    gate one way and fail it the other -- the exact bug the file-length gate
    was patched for.

    Deliberately NOT `Path.resolve()`: build and asset dirs here are symlinks
    out to sibling trees, and resolving would move those paths outside the
    repo and change which exemptions match.
    """
    return path if path.is_absolute() else Path.cwd() / path


def violations_for(path: Path) -> list[str]:
    """Every rule `path` breaks, as human-readable messages."""
    full = absolutize(path)
    problems: list[str] = []

    if is_markdown(path) and not is_exempt(full) and not has_allowed_name(path):
        problems.append("name must start with README / CLAUDE / DOCS / TODO")

    # The marker rules apply even to exempt-by-name files: a CONTRIBUTING.md
    # carrying "REMOVE ME AFTER FINISH" is a task wearing a reserved name, and
    # that is precisely the leak rule 3 exists to catch.
    if is_markdown(path):
        marked = contains_marker(full)
        if is_todo(path) and not marked:
            problems.append(f'TODO file must contain the line "{MARKER}"')
        if marked and not is_todo(path):
            problems.append(
                f'contains "{MARKER}" but is not named TODO*.md '
                "-- rename it, or drop the marker if it is not a task"
            )

    return problems


def collect(args: argparse.Namespace, parser: argparse.ArgumentParser) -> list[Path]:
    """The files to check, honouring --all and git-ignore like file_length."""
    if args.all:
        return list(iter_all(Path.cwd()))
    if args.paths:
        existing = [p for p in args.paths if p.is_file()]
        ignored = git_ignored(existing, Path.cwd())
        return [p for p in existing if p not in ignored]
    parser.error("give file paths or --all")
    raise AssertionError("unreachable")  # pragma: no cover - parser.error exits


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail if any markdown file breaks the naming convention."
    )
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument(
        "--all",
        action="store_true",
        help="check the whole tree under the current directory",
    )
    args = parser.parse_args()

    found: list[tuple[Path, str]] = []
    for path in collect(args, parser):
        if not path.is_file():
            continue
        for problem in violations_for(path):
            found.append((path, problem))

    if not found:
        return 0

    print(
        f"Markdown-naming gate FAILED: {len(found)} problem(s)\n",
        file=sys.stderr,
    )
    for path, problem in sorted(found, key=lambda item: str(item[0])):
        print(f"  {path}: {problem}", file=sys.stderr)
    print(
        "\nNamespaces: README.md, CLAUDE*.md, DOCS*.md, TODO*.md\n"
        "See ~/.claude/skills/md-file-conventions/SKILL.md",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
