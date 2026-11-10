# Copyright (c) 2026 Krzysztof Rudnicki
"""Shared fixtures-as-functions for the interview-prep tests."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import TYPE_CHECKING

import focus_project as fp

if TYPE_CHECKING:
    from pathlib import Path

START = date(2026, 11, 10)  # Tuesday: D1
TEST_DAY = date(2026, 11, 27)  # Friday: T
TEST_AT = datetime.combine(TEST_DAY, time(10, 0))
SAT1 = date(2026, 11, 14)
SAT2 = date(2026, 11, 21)


def at(day: int, hour: int = 0, minute: int = 0) -> datetime:
    """A November 2026 local datetime."""
    return datetime.combine(date(2026, 11, day), time(hour, minute))


def make(pid: str = "iv", /, **kw: object) -> fp.Project:
    """Create an interview project D1 = Nov 10, T = Nov 27."""
    args: dict[str, object] = {
        "name": "Interview",
        "start": START,
        "end": TEST_DAY,
        "replaces": ["leetcode", "reading", "tutor"],
        "daily_minutes": 120,
        "unlock_minutes": 30,
        "kind": "interview",
        "test_at": TEST_AT,
        "invite_url": "https://app.codility.com/c/run/abc",
    }
    args.update(kw)
    return fp.create_project(pid, **args)  # type: ignore[arg-type]


def shot(tmp_path: Path, name: str = "rules.png") -> Path:
    """A non-empty screenshot stand-in."""
    path = tmp_path / name
    path.write_bytes(b"\x89PNG rules")
    return path


def states(project: fp.Project, now: datetime) -> dict[str, str]:
    """Milestone id -> state."""
    return {m.id: m.state for m in fp.milestones(project, now)}
