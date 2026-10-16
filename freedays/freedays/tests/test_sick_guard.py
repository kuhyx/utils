# Copyright (c) 2026 Krzysztof Rudnicki
"""A sick day cannot be marked free; no sickdays means the mark is allowed."""

from __future__ import annotations

from datetime import date
import sys
import types

import pytest

from freedays._api import is_free_day, mark
from freedays._errors import SickDayConflictError
from freedays._sick_guard import is_sick_predicate

TODAY = date(2026, 10, 16)
SICK = date(2026, 10, 20)


def _fake_sickdays(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = types.ModuleType("sickdays")

    def _is_sick_day(day: date) -> bool:
        return day == SICK

    vars(fake)["is_sick_day"] = _is_sick_day
    monkeypatch.setitem(sys.modules, "sickdays", fake)


def test_the_predicate_is_sickdays_own(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_sickdays(monkeypatch)
    predicate = is_sick_predicate()
    assert predicate is not None
    assert predicate(SICK)
    assert not predicate(TODAY)


def test_no_sickdays_is_logged_and_allowed(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setitem(sys.modules, "sickdays", None)
    with caplog.at_level("WARNING"):
        assert is_sick_predicate() is None
    assert "sickdays is not installed" in caplog.text


def test_a_sick_day_cannot_be_marked_free(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_sickdays(monkeypatch)
    predicate = is_sick_predicate()
    monkeypatch.setattr("freedays._sick_guard.is_sick_predicate", lambda: predicate)
    with pytest.raises(SickDayConflictError, match="sickdays remove"):
        mark(SICK, now=TODAY)
    assert not is_free_day(SICK, now=TODAY)
    mark(TODAY, now=TODAY)
    assert is_free_day(TODAY, now=TODAY)


def test_without_sickdays_the_mark_goes_through() -> None:
    mark(SICK, now=TODAY)
    assert is_free_day(SICK, now=TODAY)
