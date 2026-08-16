"""Gate: fail if any given file exceeds the 250-line cap.

Invoked by `scripts/check_file_length.sh`, which pre-commit calls with the
staged files. Exits 1 and lists every violation; exits 0 silently otherwise.

The check is deliberately deterministic code rather than a judgement call --
adjudication belongs in an exit code, not in a model.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

if __package__ in (None, ""):  # invoked as a plain script
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from file_length.config import (
    CAPPED_EXTENSIONS,
    EXCLUDED_DIRS,
    MAX_LINES,
    is_data_text,
    is_generated,
    is_session_artifact,
    is_vendored,
)


def count_lines(path: Path) -> int | None:
    """Number of lines, or None if the file is binary or unreadable."""
    try:
        with path.open("rb") as handle:
            first = handle.read(8192)
            if b"\x00" in first:
                return None
            count = first.count(b"\n")
            while chunk := handle.read(1 << 20):
                count += chunk.count(b"\n")
            if first and not first.endswith(b"\n") and count == 0:
                count = 1
        return count
    except OSError:
        return None


def absolutize(path: Path) -> Path:
    """`path` anchored at the cwd, without resolving symlinks.

    The exemption rules are written against full paths ('/.claude/skills/'),
    but pre-commit passes paths relative to the repo root ('skills/x.md') while
    --all walks absolute ones. Matching a relative path against those rules
    silently drops the repo-name context, so the same file passed the gate one
    way and failed it the other.

    Deliberately NOT `Path.resolve()`: build and asset dirs here are symlinks
    out to ../testsAndMisc_builds/, and resolving would move those paths
    outside the repo and change which exemptions match.
    """
    return path if path.is_absolute() else Path.cwd() / path


def exempt_reason(path: Path, lines: int) -> str | None:
    """Why this file is not subject to the cap, or None if it is subject."""
    if path.suffix.lower() not in CAPPED_EXTENSIONS:
        return "not a capped extension"
    if is_vendored(absolutize(path)):
        return "vendored / third-party"
    if is_session_artifact(absolutize(path)):
        return "frozen session artifact"
    if is_generated(path):
        return "generated"
    try:
        size = path.stat().st_size
    except OSError:
        return "unreadable"
    if is_data_text(path, lines, size):
        return "data-ish text (wordlist)"
    return None


def git_ignored(paths: list[Path], root: Path) -> set[Path]:
    """The subset of `paths` that git ignores, empty if root is not a repo.

    Git-ignored files are build output or generated data the repo does not
    own -- an app's own export (todo's BACKLOG.md), a log, a scratch dump.
    They are rewritten wholesale by whatever produces them, so splitting one
    is meaningless: the next run restores the original. Pre-commit never sees
    them either (they cannot be staged), so skipping them makes --all agree
    with the hook instead of failing on files no commit could ever fix.
    """
    if not paths:
        return set()
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "check-ignore", "--stdin"],
            input="\n".join(str(p) for p in paths),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:  # git not installed
        return set()
    # 0 = some ignored, 1 = none ignored, 128 = not a repo.
    if result.returncode not in (0, 1):
        return set()
    return {Path(line) for line in result.stdout.splitlines() if line}


def iter_all(root: Path):
    """Every file under root, skipping excluded and git-ignored files."""
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
        for name in filenames:
            candidate = Path(dirpath) / name
            if not candidate.is_symlink():
                found.append(candidate)
    ignored = git_ignored(found, root)
    return [path for path in found if path not in ignored]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=f"Fail if any file exceeds {MAX_LINES} lines."
    )
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument(
        "--all",
        action="store_true",
        help="check the whole tree under the current directory",
    )
    parser.add_argument(
        "--explain", action="store_true", help="also report why files were skipped"
    )
    args = parser.parse_args()

    if args.all:
        targets = list(iter_all(Path.cwd()))
    elif args.paths:
        # Explicitly-named paths get the same git-ignore skip as --all, so
        # naming a file directly cannot report a violation the hook never
        # would. Without this the two modes disagree on exactly the files
        # no commit could ever fix (todo's exported BACKLOG.md, logs).
        existing = [p for p in args.paths if p.is_file()]
        ignored = git_ignored(existing, Path.cwd())
        targets = [p for p in existing if p not in ignored]
    else:
        parser.error("give file paths or --all")

    violations: list[tuple[Path, int]] = []
    for path in targets:
        if not path.is_file():
            continue
        lines = count_lines(path)
        if lines is None:
            continue
        reason = exempt_reason(path, lines)
        if reason is not None:
            if args.explain:
                print(f"  skip {path}: {reason}")
            continue
        if lines > MAX_LINES:
            violations.append((path, lines))

    if not violations:
        return 0

    print(
        f"File-length gate FAILED: {len(violations)} file(s) over {MAX_LINES} lines\n",
        file=sys.stderr,
    )
    for path, lines in sorted(violations, key=lambda item: -item[1]):
        over = lines - MAX_LINES
        print(f"  {path}: {lines} lines (over by {over})", file=sys.stderr)
    print("\nSplit them, or see refactor_claude_todo.md in this repo.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
