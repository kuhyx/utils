# Copyright (c) 2026 Krzysztof Rudnicki
"""Wording and calendar arithmetic for the picker -- no Tk in here.

Every string is the phone's (``wake-alarm/phone_app/lib/screens/
sick_day_sheet.dart`` and ``sick_days_body.dart``), so the two pickers read
the same. Kept here, apart from the widgets, so it is testable without a
display.
"""

from __future__ import annotations

import calendar
from datetime import date
from typing import TYPE_CHECKING, Final

from sickdays._conflict import free_day_predicate
from sickdays._constants import (
    LOCKER_ALARM,
    LOCKER_BOOK,
    LOCKER_DIET,
    LOCKER_LEETCODE,
    LOCKER_WORKOUT,
)
from sickdays._day import to_iso
from sickdays._errors import ConflictCheckUnavailableError

if TYPE_CHECKING:
    from collections.abc import Iterable

#: What each locker is called on screen, in ``sickdays.LOCKERS`` order.
LOCKER_LABELS: Final = {
    LOCKER_WORKOUT: "Workout lock",
    LOCKER_LEETCODE: "LeetCode",
    LOCKER_BOOK: "Book",
    LOCKER_DIET: "Diet",
    LOCKER_ALARM: "Wake alarm",
}

SHEET_HELP: Final = (
    "Off = stands down for the day. Switch on any locker that should still "
    "apply; it then behaves exactly as on a normal day."
)
INTRO: Final = (
    "Click a day to mark it sick and choose which lockers still apply; click "
    "a sick day to change them or clear it. Today or later only. No limit and "
    "no reason needed."
)
INTRO_DETAIL: Final = (
    "On a sick day every locker left off stands down: no alarm, no lock, and "
    "work left undone is dropped rather than carried forward. A locker "
    "switched on behaves as on a normal day; a dot marks a sick day that "
    "keeps one."
)
PAST_NOTE: Final = "This day has passed; it can no longer be changed."
NONE_AHEAD: Final = "None ahead."
WEEKDAY_INITIALS: Final = ("M", "T", "W", "T", "F", "S", "S")

_WEEKDAYS: Final = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
#: Tue/Wed/Thu, shaded like the phone's grid (wake-alarm's ``isWorkday``).
_WORKDAYS: Final = frozenset({1, 2, 3})


def day_label(day: date) -> str:
    """``"Tue 2026-10-20"``."""
    return f"{_WEEKDAYS[day.weekday()]} {to_iso(day)}"


def kept_label(kept: Iterable[str]) -> str:
    """The kept lockers as one line, in :data:`LOCKER_LABELS` order."""
    chosen = set(kept)
    return ", ".join(label for key, label in LOCKER_LABELS.items() if key in chosen)


def panel_title(day: date, *, sick: bool) -> str:
    """``"Mark sick: Tue 2026-10-20"``, or ``"Sick day: ..."`` when editing."""
    return f"{'Sick day' if sick else 'Mark sick'}: {day_label(day)}"


def free_day_refusal(day: date) -> str | None:
    """Why ``day`` cannot be marked sick for the free-day pool, or None.

    "Could not check" refuses too, with the library's own message: it must
    never count as "not a free day".
    """
    try:
        is_free = free_day_predicate()
    except ConflictCheckUnavailableError as exc:
        return str(exc)
    if not is_free(day):
        return None
    return f"{to_iso(day)} is a free day — release it in Free days first."


def is_workday(day: date) -> bool:
    """Whether ``day`` is a weekly workday (Tue/Wed/Thu), shaded on the grid."""
    return day.weekday() in _WORKDAYS


def month_title(month: date) -> str:
    """``"October 2026"``."""
    return f"{calendar.month_name[month.month]} {month.year}"


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
