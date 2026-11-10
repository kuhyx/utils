# Copyright (c) 2026 Krzysztof Rudnicki
"""Project kinds and the interview budget (the one place the numbers live)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date

FOCUS = "focus"
INTERVIEW = "interview"
KINDS = frozenset({FOCUS, INTERVIEW})

# kuhy, 2026-11-10: near-zero weekday energy, weekends are for learning.
WEEKDAY_MINUTES = 30
WEEKEND_MINUTES = 120
_FIRST_WEEKEND_DAY = 5  # Saturday


def interview_minutes(day: date) -> int:
    """The daily target of an interview project on ``day`` (Sat/Sun = 120)."""
    return WEEKEND_MINUTES if day.weekday() >= _FIRST_WEEKEND_DAY else WEEKDAY_MINUTES
