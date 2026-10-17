# Copyright (c) 2026 Krzysztof Rudnicki
"""The picker's wording, calendar arithmetic and tokens -- no display needed."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sickdays._errors import ConflictCheckUnavailableError
from sickdays.gui import _text
from sickdays.gui import _tokens as tok

if TYPE_CHECKING:
    import pytest

DAY = date(2026, 10, 20)


def test_labels_match_the_phone() -> None:
    assert _text.day_label(DAY) == "Tue 2026-10-20"
    assert _text.panel_title(DAY, sick=False) == "Mark sick: Tue 2026-10-20"
    assert _text.panel_title(DAY, sick=True) == "Sick day: Tue 2026-10-20"
    assert list(_text.LOCKER_LABELS.values()) == [
        "Workout lock",
        "LeetCode",
        "Book",
        "Diet",
        "Wake alarm",
    ]


def test_kept_label_follows_locker_order_not_the_alphabet() -> None:
    assert _text.kept_label({"alarm", "book", "workout"}) == (
        "Workout lock, Book, Wake alarm"
    )
    assert _text.kept_label(frozenset()) == ""


def test_free_day_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _text.free_day_refusal(DAY) is None
    monkeypatch.setattr(
        "sickdays.gui._text.free_day_predicate", lambda: lambda _d: True
    )
    assert _text.free_day_refusal(DAY) == (
        "2026-10-20 is a free day — release it in Free days first."
    )

    def unavailable() -> None:
        msg = "freedays is not installed"
        raise ConflictCheckUnavailableError(msg)

    monkeypatch.setattr("sickdays.gui._text.free_day_predicate", unavailable)
    assert _text.free_day_refusal(DAY) == "freedays is not installed"


def test_month_grid_is_monday_first() -> None:
    weeks = _text.month_weeks(date(2026, 10, 1))
    assert weeks[0] == [None, None, None, *(date(2026, 10, d) for d in (1, 2, 3, 4))]
    assert weeks[-1][-1] is None
    assert _text.month_title(date(2026, 10, 1)) == "October 2026"


def test_month_arithmetic_and_range() -> None:
    assert _text.shift_month(date(2026, 12, 1), 1) == date(2027, 1, 1)
    assert _text.shift_month(date(2026, 1, 1), -1) == date(2025, 12, 1)
    assert _text.month_bounds(DAY) == (date(2026, 1, 1), date(2027, 12, 1))


def test_workdays_are_tuesday_to_thursday() -> None:
    assert [_text.is_workday(date(2026, 10, d)) for d in range(19, 26)] == [
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
