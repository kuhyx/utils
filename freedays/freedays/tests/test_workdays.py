# Copyright (c) 2026 Krzysztof Rudnicki
"""The weekly workdays: the one Tue/Wed/Thu definition every app reads."""

from __future__ import annotations

from datetime import date

import pytest

import freedays


def test_workdays_are_tuesday_to_thursday() -> None:
    assert frozenset({1, 2, 3}) == freedays.WORKDAYS


def test_non_workdays_are_the_complement() -> None:
    assert frozenset({0, 4, 5, 6}) == freedays.NON_WORKDAYS
    assert not freedays.WORKDAYS & freedays.NON_WORKDAYS


@pytest.mark.parametrize(
    "day",
    [date(2026, 9, 29), date(2026, 9, 30), date(2026, 10, 1)],  # Tue, Wed, Thu
)
def test_tuesday_to_thursday_are_workdays(day: date) -> None:
    assert freedays.is_workday(day)


@pytest.mark.parametrize(
    "day",
    # Mon, Fri, Sat, Sun
    [date(2026, 9, 28), date(2026, 10, 2), date(2026, 10, 3), date(2026, 10, 4)],
)
def test_the_rest_are_not(day: date) -> None:
    assert not freedays.is_workday(day)


def test_is_workday_defaults_to_today() -> None:
    assert freedays.is_workday() is (freedays.today().weekday() in {1, 2, 3})
