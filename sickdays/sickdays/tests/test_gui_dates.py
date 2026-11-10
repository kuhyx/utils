# Copyright (c) 2026 Krzysztof Rudnicki
"""The picker's calendar arithmetic, free-day check and tokens -- no display."""

from __future__ import annotations

from datetime import date
import logging
from typing import TYPE_CHECKING

from sickdays._errors import ConflictCheckUnavailableError
from sickdays.gui import _dates
from sickdays.gui import _tokens as tok

if TYPE_CHECKING:
    import pytest

DAY = date(2026, 10, 20)


def test_kept_lockers_follow_locker_order_not_the_alphabet() -> None:
    assert _dates.kept_in_order({"alarm", "book", "workout"}) == (
        "workout",
        "book",
        "alarm",
    )
    assert _dates.kept_in_order(frozenset()) == ()


def test_free_day_block(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    assert _dates.free_day_block(DAY) is None
    monkeypatch.setattr(
        "sickdays.gui._dates.free_day_predicate", lambda: lambda _d: True
    )
    assert _dates.free_day_block(DAY) == "free"

    def unavailable() -> None:
        msg = "freedays is not installed"
        raise ConflictCheckUnavailableError(msg)

    monkeypatch.setattr("sickdays.gui._dates.free_day_predicate", unavailable)
    with caplog.at_level(logging.WARNING):
        assert _dates.free_day_block(DAY) == "unavailable"
    assert "freedays is not installed" in caplog.text


def test_month_grid_is_monday_first() -> None:
    weeks = _dates.month_weeks(date(2026, 10, 1))
    assert weeks[0] == [None, None, None, *(date(2026, 10, d) for d in (1, 2, 3, 4))]
    assert weeks[-1][-1] is None
    assert _dates.month_title(date(2026, 10, 1)) == "2026-10"
    assert _dates.month_title(date(2027, 3, 1)) == "2027-03"
    assert [_dates.is_weekend_column(c) for c in range(7)] == [
        False,
        False,
        False,
        False,
        False,
        True,
        True,
    ]


def test_month_arithmetic_and_range() -> None:
    assert _dates.shift_month(date(2026, 12, 1), 1) == date(2027, 1, 1)
    assert _dates.shift_month(date(2026, 1, 1), -1) == date(2025, 12, 1)
    assert _dates.month_bounds(DAY) == (date(2026, 1, 1), date(2027, 12, 1))


def test_workdays_are_tuesday_to_thursday() -> None:
    assert [_dates.is_workday(date(2026, 10, d)) for d in range(19, 26)] == [
        False,
        True,
        True,
        True,
        False,
        False,
        False,
    ]


def test_tokens() -> None:
    assert tok.font("Fake Sans", "body") == ("Fake Sans", -16, "normal")
    assert tok.font("Fake Sans", "title", bold=True) == ("Fake Sans", -24, "bold")
    assert tok.blend("#FFFFFF", "#000000", 0.5) == "#808080"
    assert tok.blend(tok.SICK, tok.INK, 1.0) == tok.SICK
