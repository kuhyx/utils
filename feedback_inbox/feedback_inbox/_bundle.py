# Copyright (c) 2026 Krzysztof Rudnicki
"""Finding games' feedback folders and bundles, and the stamp arithmetic."""

from __future__ import annotations

from datetime import datetime, timedelta
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

BINARIES_SUFFIX = "_binaries"
STAMP_FORMAT = "%Y-%m-%dT%H-%M-%S"
_STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}-\d{3}$")
_REMINDER_HOUR = 10


def binaries_dirs(data_root: Path) -> list[Path]:
    """Every ``<game>_binaries`` directory directly under ``data_root``."""
    if not data_root.is_dir():
        return []
    return sorted(
        p
        for p in data_root.iterdir()
        if p.name.endswith(BINARIES_SUFFIX) and p.is_dir()
    )


def feedback_dirs(data_root: Path) -> list[Path]:
    """Every existing ``<game>_binaries/feedback`` directory."""
    return [
        d / "feedback" for d in binaries_dirs(data_root) if (d / "feedback").is_dir()
    ]


def repo_name(feedback_dir: Path) -> str:
    """The game's repo name: ``cleanup-plate_binaries`` -> ``cleanup-plate``."""
    return feedback_dir.parent.name.removesuffix(BINARIES_SUFFIX)


def bundles_in(feedback_dir: Path) -> list[Path]:
    """Bundle folders (named by a millisecond stamp), oldest first."""
    return sorted(
        p for p in feedback_dir.iterdir() if p.is_dir() and _STAMP.match(p.name)
    )


def parse_stamp(stamp: str) -> datetime:
    """The local time a bundle was saved, from its folder name."""
    return datetime.strptime(stamp[:19], STAMP_FORMAT)


def due_at(stamp: str) -> datetime:
    """The reminder time: the day after the bundle, at 10:00 local."""
    day = parse_stamp(stamp) + timedelta(days=1)
    return day.replace(hour=_REMINDER_HOUR, minute=0, second=0, microsecond=0)
