# Copyright (c) 2026 Krzysztof Rudnicki
"""The weekly workdays: the one Tue/Wed/Thu definition every app reads."""

from __future__ import annotations

from datetime import date

import pytest

import freedays


def test_workdays_are_tuesday_to_thursday() -> None:
    assert freedays.WORKDAYS == frozenset({1, 2, 3})


def test_non_workdays_are_the_complement() -> None:
    assert freedays.NON_WORKDAYS == frozenset({0, 4, 5, 6})
    assert not freedays.WORKDAYS & freedays.NON_WORKDAYS


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 9, 28), False),  # Monday
        (date(2026, 9, 29), True),  # Tuesday
        (date(2026, 9, 30), True),  # Wednesday
        (date(2026, 10, 1), True),  # Thursday
        (date(2026, 10, 2), False),  # Friday
        (date(2026, 10, 3), False),  # Saturday
        (date(2026, 10, 4), False),  # Sunday
    ],
)
def test_is_workday(day: date, expected: bool) -> None:
    assert freedays.is_workday(day) is expected


def test_is_workday_defaults_to_today() -> None:
    assert freedays.is_workday() is (date.today().weekday() in {1, 2, 3})
