# Copyright (c) 2026 Krzysztof Rudnicki
"""The weekly workdays: Tuesday, Wednesday and Thursday.

The one definition every gate app reads, so "which days are workdays" cannot
drift between them. Consumers each give it their own meaning: screen-locker
relaxes the lock, leetcode-guard charges the cheap price, wake-alarm's ramp
holds the wake time instead of stepping it earlier, and a missed workday
morning costs tomorrow its leniency.

Languages that cannot import this package (the Dart and Kotlin sides of the
phone apps) keep a literal copy and a test that fails when it drifts from
this one.
"""

from __future__ import annotations

from datetime import date
from typing import Final

from freedays._day import today

#: Python ``date.weekday()`` numbering: Mon=0 ... Sun=6.
WORKDAYS: Final[frozenset[int]] = frozenset({1, 2, 3})

#: The complement: Monday, Friday, Saturday and Sunday.
NON_WORKDAYS: Final[frozenset[int]] = frozenset(range(7)) - WORKDAYS


def is_workday(day: date | None = None) -> bool:
    """Return whether *day* (default: today, local) is a weekly workday.

    Args:
        day: The date to classify; ``None`` means today.

    Returns:
        True on Tuesday, Wednesday and Thursday.
    """
    return today(day).weekday() in WORKDAYS
