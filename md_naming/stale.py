"""Report TODO files that have sat untouched for too long.

CI cannot prove a task is finished -- no exit code exists for "done" -- so the
honest mechanism is a nudge, not a gate. This module only ever emits GitHub
`::warning::` lines and exits 0, deliberately: a build that fails because a
task is merely *old* trains people to ignore it.

Ages come from the last git commit that touched the file, not mtime, because
a checkout rewrites every mtime to the clone time.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - plain-script import path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from file_length.check import iter_all
from md_naming.config import STALE_DAYS, is_todo


def last_commit_epoch(path: Path, root: Path) -> int | None:
    """Unix time of the last commit touching `path`, or None if unknown."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "log", "-1", "--format=%ct", "--", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:  # git not installed
        return None
    if result.returncode != 0:
        return None
    stamp = result.stdout.strip()
    return int(stamp) if stamp.isdigit() else None


def age_days(path: Path, root: Path, now: int) -> int | None:
    """Whole days since `path` was last committed, or None if unknown."""
    epoch = last_commit_epoch(path, root)
    if epoch is None:
        return None
    return (now - epoch) // 86_400


def stale_todos(root: Path, limit: int, now: int) -> list[tuple[Path, int]]:
    """Every TODO under `root` older than `limit` days, oldest first."""
    found: list[tuple[Path, int]] = []
    for path in iter_all(root):
        if not is_todo(path):
            continue
        days = age_days(path, root, now)
        if days is not None and days >= limit:
            found.append((path, days))
    return sorted(found, key=lambda item: -item[1])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Warn about TODO files older than the staleness limit."
    )
    parser.add_argument("--days", type=int, default=STALE_DAYS)
    args = parser.parse_args()

    root = Path.cwd()
    now = int(datetime.now(tz=timezone.utc).timestamp())
    for path, days in stale_todos(root, args.days, now):
        rel = path.relative_to(root) if path.is_relative_to(root) else path
        print(
            f"::warning file={rel}::{rel} is {days} days old. "
            "Still outstanding? If the work landed, delete this file."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
