# Copyright (c) 2026 Krzysztof Rudnicki
"""An edit never lowers today's obligation: reductions apply from tomorrow."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytest

import focus_project as fp

START = date(2026, 11, 2)
TODAY = date(2026, 11, 4)
TOMORROW = TODAY + timedelta(days=1)
YESTERDAY = TODAY - timedelta(days=1)
END = date(2026, 11, 20)


def _make(start: date = START, replaces: list[str] | None = None) -> fp.Project:
    return fp.create_project(
        "p",
        name="P",
        start=start,
        end=END,
        replaces=replaces or ["leetcode"],
        daily_minutes=120,
        unlock_minutes=30,
    )


def _noon(day: date) -> float:
    return datetime.combine(day, time(12)).timestamp()


def _limits(day: date) -> tuple[int, int, tuple[str, ...]]:
    p = fp.list_projects()[0]
    return p.daily_on(day), p.unlock_on(day), p.replaces_on(day)


def test_red_team_unlock_zero_waits_for_tomorrow() -> None:
    _make()
    got = fp.apply_update("p", today=TODAY, unlock_minutes=0)
    assert got.effective_from == TOMORROW
    assert _limits(TODAY)[1] == 30
    assert _limits(YESTERDAY)[1] == 30
    assert _limits(TOMORROW)[1] == 0
    assert fp.status(TODAY)["unlock_minutes"] == 30


def test_one_minute_day_does_not_change_today() -> None:
    _make()
    fp.record_activity("tutor", "heartbeat", ts=_noon(TODAY), project="p")
    before = fp.status(TODAY)
    fp.update_project("p", today=TODAY, daily_minutes=1, unlock_minutes=0)
    after = fp.status(TODAY)
    assert after == before
    assert after["daily_minutes"] == 120
    assert fp.minutes_for(TODAY) == before["counted_minutes"]
    assert fp.status(TOMORROW)["daily_minutes"] == 1


def test_raises_apply_today() -> None:
    _make()
    got = fp.apply_update("p", today=TODAY, daily_minutes=180, unlock_minutes=40)
    assert got.effective_from == TODAY
    assert _limits(TODAY)[:2] == (180, 40)
    assert _limits(YESTERDAY)[:2] == (120, 30)


def test_mixed_edit_defers_whole_edit() -> None:
    _make()
    got = fp.apply_update("p", today=TODAY, daily_minutes=180, unlock_minutes=10)
    assert got.effective_from == TOMORROW
    assert _limits(TODAY)[:2] == (120, 30)
    assert _limits(TOMORROW)[:2] == (180, 10)


def test_added_gate_waits_removed_gate_is_immediate() -> None:
    _make(replaces=["leetcode", "reading"])
    got = fp.apply_update("p", today=TODAY, replaces=["leetcode", "reading", "tutor"])
    assert got.effective_from == TOMORROW
    assert not fp.stands_down("tutor", TODAY)
    assert fp.stands_down("tutor", TOMORROW)
    assert fp.status(TODAY)["replaces"] == ["leetcode", "reading"]
    got = fp.apply_update("p", today=TODAY, replaces=["leetcode"])
    assert got.effective_from == TODAY
    assert not fp.stands_down("reading", TODAY)
    assert not fp.stands_down("reading", TOMORROW)
    assert fp.stands_down("reading", YESTERDAY)


def test_pending_cut_then_second_edits_the_same_day() -> None:
    _make()
    fp.update_project("p", today=TODAY, daily_minutes=60, unlock_minutes=10)
    assert _limits(TODAY)[:2] == (120, 30)
    # a smaller cut than E is still a cut; a deeper cut still waits
    fp.update_project("p", today=TODAY, daily_minutes=50)
    assert _limits(TODAY)[:2] == (120, 30)
    assert _limits(TOMORROW)[:2] == (50, 10)
    assert len(fp.list_projects()[0].history) == 1
    # a name-only edit leaves the pending cut alone
    assert fp.apply_update("p", today=TODAY, name="Q").effective_from == TODAY
    assert _limits(TOMORROW)[:2] == (50, 10)
    # back up to (or over) today's targets cancels the pending cut, applies now
    got = fp.apply_update("p", today=TODAY, daily_minutes=120, unlock_minutes=30)
    assert got.effective_from == TODAY
    assert fp.list_projects()[0].history == ()
    got = fp.apply_update("p", today=TODAY, daily_minutes=60)
    got = fp.apply_update("p", today=TODAY, daily_minutes=200)
    assert got.effective_from == TODAY
    assert _limits(TODAY)[:2] == (200, 30)
    assert _limits(YESTERDAY)[:2] == (120, 30)


def test_not_yet_started_project_is_a_new_obligation() -> None:
    _make(start=TOMORROW)
    got = fp.apply_update("p", today=TODAY, daily_minutes=10, unlock_minutes=0)
    assert got.effective_from == TODAY
    assert fp.list_projects()[0].history == ()
    assert _limits(TOMORROW)[:2] == (10, 0)


def test_project_starting_today_defers_a_cut() -> None:
    _make(start=TODAY)
    got = fp.apply_update("p", today=TODAY, daily_minutes=1, unlock_minutes=0)
    assert got.effective_from == TOMORROW
    assert _limits(TODAY)[:2] == (120, 30)


def test_early_end_keeps_today_covered() -> None:
    _make()
    fp.update_project("p", today=TODAY, end=TODAY)
    assert fp.active(TODAY) is not None
    assert fp.active(TOMORROW) is None
    with pytest.raises(ValueError, match="past"):
        fp.update_project("p", today=TODAY, end=YESTERDAY)


def test_legacy_history_row_without_replaces_round_trips() -> None:
    old = {"until": "2026-11-03", "daily_minutes": 5, "unlock_minutes": 1}
    row = fp.Limits.from_dict(old)
    assert row.replaces is None
    assert "replaces" not in row.to_dict()
    with_r = fp.Limits(YESTERDAY, 5, 1, ("tutor",))
    assert fp.Limits.from_dict(with_r.to_dict()) == with_r
