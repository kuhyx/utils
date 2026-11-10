# Copyright (c) 2026 Krzysztof Rudnicki
"""Milestone generation, states and the lock that falls out of them."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import focus_project as fp
from focus_project import evidence
from focus_project.tests.helpers import SAT1, SAT2, at, make, shot, states

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _due(p: fp.Project, now_day: int = 10) -> dict[str, str]:
    return {m.id: m.due.isoformat() for m in fp.milestones(p, at(now_day, 8))}


def test_table_of_dues() -> None:
    assert _due(make()) == {
        "rules": "2026-11-10T23:59:00",
        "trip_ask:2026-11-14": "2026-11-12T23:59:00",
        "trip_ask:2026-11-21": "2026-11-19T23:59:00",
        "mock": "2026-11-25T23:59:00",
        "slot": "2026-11-26T12:00:00",
    }


def test_sorted_by_due_and_all_pending_at_start() -> None:
    project = make()
    items = fp.milestones(project, at(10, 8))
    assert [m.due for m in items] == sorted(m.due for m in items)
    assert {m.state for m in items} == {"pending"}
    assert items[0].to_dict() == {
        "id": "rules",
        "due": "2026-11-10T23:59:00",
        "state": "pending",
    }


def test_focus_project_has_none() -> None:
    p = fp.create_project(
        "f",
        name="F",
        start=date(2026, 11, 10),
        end=date(2026, 11, 12),
        replaces=["leetcode"],
        daily_minutes=30,
        unlock_minutes=10,
    )
    assert fp.milestones(p, at(11, 8)) == []


def test_unanswered_weekend_is_a_trip_once_ask_is_due() -> None:
    p = make()
    assert "phone:2026-11-14" not in states(p, at(12, 23, 58))
    got = states(p, at(13, 8))
    assert got["trip_ask:2026-11-14"] == "missed"
    assert got["phone:2026-11-14"] == "pending"  # due Fri 12:00
    assert states(p, at(13, 12))["phone:2026-11-14"] == "missed"
    assert _due(p, 13)["phone:2026-11-14"] == "2026-11-13T12:00:00"


def test_answers_decide_the_phone_milestone() -> None:
    make()
    no = fp.answer_weekend("iv", SAT1, trip=False, now=at(11, 9))
    assert "phone:2026-11-14" not in states(no, at(13, 13))
    assert states(no, at(13, 13))["trip_ask:2026-11-14"] == "done"
    yes = fp.answer_weekend("iv", SAT1, trip=True, now=at(11, 10))
    assert states(yes, at(11, 11))["phone:2026-11-14"] == "pending"


def test_explicit_trip_covers_its_saturday() -> None:
    make()
    p = fp.add_trip("iv", date(2026, 11, 13), date(2026, 11, 15), now=at(10, 9))
    got = states(p, at(13, 8))
    assert "phone:2026-11-13" in got
    assert "phone:2026-11-14" not in got
    assert _due(p)["phone:2026-11-13"] == "2026-11-12T12:00:00"


def test_late_trip_is_due_the_moment_it_is_entered() -> None:
    make()
    p = fp.add_trip("iv", date(2026, 11, 13), date(2026, 11, 14), now=at(12, 8))
    assert _due(p, 12)["phone:2026-11-13"] == "2026-11-12T08:00:00"
    assert states(p, at(12, 8))["phone:2026-11-13"] == "missed"
    far = fp.add_trip("iv", date(2026, 11, 20), date(2026, 11, 22), now=at(12, 9))
    assert _due(far, 12)["phone:2026-11-20"] == "2026-11-19T12:00:00"


def _clean(tmp_path: Path) -> None:
    """Everything due before the slot is done on time; weekend 2 is no trip."""
    fp.record_evidence("iv", "rules", "file", file=shot(tmp_path), now=at(10, 9))
    fp.answer_weekend("iv", SAT1, trip=False, now=at(11, 9))
    fp.answer_weekend("iv", SAT2, trip=False, now=at(11, 9))
    fp.record_evidence("iv", "mock", "score", 70, now=at(24, 9))


def test_slot_is_due_t_minus_1_at_noon_and_locks_that_evening(tmp_path: Path) -> None:
    make()
    _clean(tmp_path)
    assert fp.owed_lock(at(26, 11, 59)) is None
    owed = fp.owed_lock(at(26, 12))
    assert owed is not None
    assert owed.id == "slot"
    assert owed.state == "missed"
    assert fp.owed_lock(at(26, 20)) is not None


def test_test_day_never_locks_but_shows_red(tmp_path: Path) -> None:
    make()
    assert fp.owed_lock(at(27, 9)) is None
    assert fp.status(date(2026, 11, 27))["milestones"] is not None
    assert {m.state for m in fp.milestones(fp.list_projects()[0], at(27, 9))} >= {
        "missed"
    }


def test_owed_lock_is_the_earliest_missed() -> None:
    make()
    owed = fp.owed_lock(at(13, 8))
    assert owed is not None
    assert owed.id == "rules"


def test_late_completion_unlocks(tmp_path: Path) -> None:
    make()
    fp.answer_weekend("iv", SAT1, trip=False, now=at(11, 9))
    owed = fp.owed_lock(at(11, 10))
    assert owed is not None
    assert owed.id == "rules"
    fp.record_evidence("iv", "rules", "file", file=shot(tmp_path), now=at(11, 10))
    p = fp.list_projects()[0]
    assert states(p, at(11, 10))["rules"] == "late_done"
    assert fp.owed_lock(at(11, 10, 1)) is None


def test_on_time_is_done_at_the_boundary(tmp_path: Path) -> None:
    make()
    fp.record_evidence("iv", "rules", "file", file=shot(tmp_path), now=at(10, 23, 58))
    p = fp.list_projects()[0]
    assert states(p, at(11, 8))["rules"] == "done"
    assert states(p, at(10, 23, 59))["rules"] == "done"


def test_mock_needs_a_score(tmp_path: Path) -> None:
    p = make()
    assert states(p, at(26, 8))["mock"] == "missed"
    fp.record_evidence("iv", "mock", "score", 64, now=at(26, 8))
    assert states(fp.list_projects()[0], at(26, 9))["mock"] == "late_done"


def test_slot_needs_entry_and_confirm_tap() -> None:
    p = make()
    fp.record_evidence("iv", "slot", "slot", "2026-11-26T20:00:00", now=at(25, 9))
    assert states(p, at(25, 10))["slot"] == "pending"
    assert states(p, at(26, 12))["slot"] == "missed"  # entered, never confirmed
    fp.record_evidence("iv", "slot", "slot_confirm", value=True, now=at(25, 11))
    assert states(p, at(25, 12))["slot"] == "done"
    fp.record_evidence("iv", "slot", "slot", "2026-11-26T21:00:00", now=at(25, 13))
    assert states(p, at(25, 14))["slot"] == "pending"  # moved: confirm again
    fp.record_evidence("iv", "slot", "slot_confirm", value=True, now=at(26, 13))
    assert states(p, at(26, 14))["slot"] == "late_done"
    assert not [s for s in states(p, at(26, 14)).values() if s == "unknown"]


def _phone_setup() -> None:
    make()
    fp.answer_weekend("iv", SAT1, trip=True, now=at(11, 9))


def test_phone_milestone_states() -> None:
    _phone_setup()
    p = fp.list_projects()[0]
    mid = "phone:2026-11-14"
    assert states(p, at(13, 13))[mid] == "missed"  # no tap, no check
    fp.record_evidence("iv", mid, "tap", value=True, now=at(12, 9))
    assert states(p, at(13, 13))[mid] == "unknown"  # tap but nothing checked
    evidence.append("iv", mid, "check", value=False, now=at(13, 11))
    assert states(p, at(13, 13))[mid] == "missed"  # checked and failing
    evidence.append("iv", mid, "check", value=None, now=at(13, 11, 30))
    assert states(p, at(13, 13))[mid] == "unknown"  # source went dark
    evidence.append("iv", mid, "check", value=True, now=at(13, 11, 40))
    assert states(p, at(13, 13))[mid] == "done"


def test_phone_passed_after_due_is_late_done() -> None:
    _phone_setup()
    mid = "phone:2026-11-14"
    fp.record_evidence("iv", mid, "tap", value=True, now=at(12, 9))
    evidence.append("iv", mid, "check", value=True, now=at(13, 14))
    assert states(fp.list_projects()[0], at(13, 15))[mid] == "late_done"


def test_unknown_locks_like_missed(tmp_path: Path) -> None:
    _phone_setup()
    mid = "phone:2026-11-14"
    fp.record_evidence("iv", "rules", "file", file=shot(tmp_path), now=at(10, 9))
    fp.answer_weekend("iv", SAT2, trip=False, now=at(11, 9))
    fp.record_evidence("iv", mid, "tap", value=True, now=at(12, 9))
    owed = fp.owed_lock(at(13, 13))
    assert owed is not None
    assert (owed.id, owed.state) == (mid, "unknown")


def test_unreadable_registry_fails_open_and_loud(
    data: Path, caplog: pytest.LogCaptureFixture
) -> None:
    data.mkdir()
    (data / "projects.json").write_text("{nope")
    with caplog.at_level("WARNING"):
        assert fp.owed_lock(at(13, 8)) is None
    assert "unreadable" in caplog.text


def test_no_project_no_lock() -> None:
    assert fp.owed_lock(at(13, 8)) is None


def test_focus_project_never_locks_on_milestones() -> None:
    fp.create_project(
        "f",
        name="F",
        start=date(2026, 11, 10),
        end=date(2026, 11, 20),
        replaces=["leetcode"],
        daily_minutes=30,
        unlock_minutes=10,
    )
    assert fp.owed_lock(at(13, 8)) is None
