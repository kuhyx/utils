# Copyright (c) 2026 Krzysztof Rudnicki
"""Focus project: fail mode, row matching, per-day target."""

from __future__ import annotations

from datetime import date, timedelta
import logging
import sys
from types import SimpleNamespace

import pytest

from earned_time import TUTOR_EARNERS, day_window, earners_for
from earned_time._match import focus_match, focus_minutes
from earned_time.tests._focus_fakes import DAY, START, activate, project, row
from earned_time.tests._maturity_rows import signed


@pytest.mark.parametrize("failure", [ImportError("gone"), ValueError("bad json")])
def test_a_broken_focus_project_means_no_project_and_logs_once(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    failure: Exception,
) -> None:
    def broken(_day: date) -> object:
        raise failure

    monkeypatch.setitem(sys.modules, "focus_project", SimpleNamespace(active=broken))
    monkeypatch.setattr("earned_time._focus._warned", set())
    with caplog.at_level(logging.WARNING):
        assert earners_for(DAY) is TUTOR_EARNERS
        assert earners_for(DAY) is TUTOR_EARNERS
    assert sum("behaving as if no project" in m for m in caplog.messages) == 1


def test_a_missing_package_is_no_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "focus_project", None)
    assert earners_for(DAY) is TUTOR_EARNERS


def test_rows_count_by_ended_at_then_by_day(caplog: pytest.LogCaptureFixture) -> None:
    window = day_window(DAY)
    assert focus_match(row(5, 5), window)
    assert not focus_match(row(5, 5, START), window)
    nostamp = signed(
        {"kind": "credit", "day": DAY.isoformat(), "detail": {"minutes": 5}}
    )
    assert focus_match(nostamp, window)
    assert not focus_match({**nostamp, "day": START.isoformat()}, window)
    with caplog.at_level(logging.WARNING):
        assert not focus_match(row(0, 1), window)
    assert "bad minutes" in caplog.text


@pytest.mark.parametrize("bad", [0, -1, True, 1.5, "5", None])
def test_minutes_must_be_a_positive_int(bad: object) -> None:
    assert focus_minutes({"detail": {"minutes": bad}}) is None
    assert focus_minutes({"detail": "x"}) is None
    assert focus_minutes({"detail": {"minutes": 4}}) == 4


def edited(day: date) -> int:
    """A target cut from 120 to 60 minutes after ``DAY``."""
    return 120 if day <= DAY else 60


def test_a_target_edit_never_reprices_past_days(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    activate(monkeypatch, project(daily_on=edited, daily_minutes=60))
    before = earners_for(DAY)[-1]
    after = earners_for(DAY + timedelta(days=1))[-1]
    assert (before.max_units, before.gaming_for(60)) == (120, 120)
    assert (after.max_units, after.gaming_for(60)) == (60, 240)
    assert (before.shutdown_for(60, DAY), after.shutdown_for(30, DAY)) == (90, 90)


def test_a_zero_target_on_a_day_changes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    activate(monkeypatch, project(daily_on=lambda _day: 0))
    assert earners_for(DAY) is TUTOR_EARNERS
