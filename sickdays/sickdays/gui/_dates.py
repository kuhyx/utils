# Copyright (c) 2026 Krzysztof Rudnicki
"""Calendar arithmetic and the free-day check for the picker -- no Tk in here.

The picker shows no words (kuhy's textgate rule): dates are ISO numerals and
a refusal is a reason *code* the widgets turn into an icon. The library's
own message for an unavailable check goes to the log, not the screen.
"""

from __future__ import annotations

import calendar
from datetime import date
import logging
from typing import TYPE_CHECKING, Final, Literal

from sickdays._conflict import free_day_predicate
from sickdays._constants import LOCKERS
from sickdays._errors import ConflictCheckUnavailableError

if TYPE_CHECKING:
    from collections.abc import Iterable

_LOG = logging.getLogger(__name__)

#: Why a day cannot be marked sick: it is a free day, or that cannot be checked.
Block = Literal["free", "unavailable"]

#: Tue/Wed/Thu, shaded like the phone's grid (wake-alarm's ``isWorkday``).
_WORKDAYS: Final = frozenset({1, 2, 3})
#: Sat/Sun, marked with a ring instead of a dot over the grid.
_WEEKEND: Final = frozenset({5, 6})


def kept_in_order(kept: Iterable[str]) -> tuple[str, ...]:
    """The kept lockers in ``sickdays.LOCKERS`` order, not the set's."""
    chosen = set(kept)
    return tuple(locker for locker in LOCKERS if locker in chosen)


def free_day_block(day: date) -> Block | None:
    """Why ``day`` cannot be marked sick for the free-day pool, or None.

    "Could not check" refuses too: it must never count as "not a free day".
    """
    try:
        is_free = free_day_predicate()
    except ConflictCheckUnavailableError as exc:
        _LOG.warning("free-day check unavailable: %s", exc)
        return "unavailable"
    return "free" if is_free(day) else None


def is_workday(day: date) -> bool:
    """Whether ``day`` is a weekly workday (Tue/Wed/Thu), shaded on the grid."""
    return day.weekday() in _WORKDAYS


def is_weekend_column(column: int) -> bool:
    """Whether grid ``column`` (0 = Monday) is Saturday or Sunday."""
    return column in _WEEKEND


def month_title(month: date) -> str:
    """``"2026-10"``: the month as numerals, never a month name."""
    return f"{month.year}-{month.month:02d}"


def month_weeks(month: date) -> list[list[date | None]]:
    """The month as Monday-first weeks, ``None`` padding either end."""
    return [
        [None if not cell else date(month.year, month.month, cell) for cell in week]
        for week in calendar.Calendar(firstweekday=0).monthdayscalendar(
            month.year, month.month
        )
    ]


def shift_month(month: date, step: int) -> date:
    """The first of the month ``step`` months after ``month``."""
    index = month.year * 12 + month.month - 1 + step
    return date(index // 12, index % 12 + 1, 1)


def month_bounds(reference: date) -> tuple[date, date]:
    """January this year to December next year, the phone's range."""
    return date(reference.year, 1, 1), date(reference.year + 1, 12, 1)
