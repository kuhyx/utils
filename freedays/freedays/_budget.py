# Copyright (c) 2026 Krzysztof Rudnicki
"""Calendar-year accounting for the pool.

One global pool, shared by every app: a day is either free everywhere or
free nowhere. The budget resets on Jan 1 and unused days do not carry over,
which is the employer-leave model people already have in their heads --
deliberately *not* a rolling window, because "how many do I have left"
should be answerable without knowing what you did eleven months ago.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from freedays._constants import DEFAULT_ANNUAL_BUDGET
from freedays._model import is_consumed_record, is_free_record, to_free_day

if TYPE_CHECKING:
    from datetime import date

    from crdt_sync import Log


def free_days_in_year(log: Log, year: int) -> list[date]:
    """Return every currently-free date in ``year``, ascending."""
    days: list[date] = []
    for record in log.values():
        if not is_free_record(record):
            continue
        free_day = to_free_day(record)
        if free_day is not None and free_day.day.year == year:
            days.append(free_day.day)
    return sorted(days)


def spent_days_in_year(log: Log, year: int) -> list[date]:
    """Every date in ``year`` that counts against the budget, ascending.

    Two kinds count: days still marked free, and days that were released
    *after* they had already arrived. The second kind is why this is not
    simply :func:`free_days_in_year` -- taking Monday off and clearing the
    entry on Tuesday does not give Monday back.
    """
    days: list[date] = []
    for record in log.values():
        free_day = to_free_day(record)
        if free_day is None or free_day.day.year != year:
            continue
        if is_free_record(record) or is_consumed_record(record):
            days.append(free_day.day)
    return sorted(days)


def spent(log: Log, year: int) -> int:
    """How many of ``year``'s free days are gone -- claimed or already used."""
    return len(spent_days_in_year(log, year))


def remaining(log: Log, year: int, *, budget: int = DEFAULT_ANNUAL_BUDGET) -> int:
    """How many free days ``year`` has left, never below zero.

    Clamped at zero so a budget lowered after the fact -- or a log merged
    from a device that had a larger one -- reads as "none left" rather than
    as a negative number that some caller will eventually treat as a count.
    """
    return max(0, budget - spent(log, year))


def is_exhausted(log: Log, year: int, *, budget: int = DEFAULT_ANNUAL_BUDGET) -> bool:
    """Whether ``year`` has no free days left to claim."""
    return remaining(log, year, budget=budget) <= 0
