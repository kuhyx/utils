# Copyright (c) 2026 Krzysztof Rudnicki
"""Project.kind, interview fields, validation, budget."""

from __future__ import annotations

from datetime import date
import json
from typing import TYPE_CHECKING

import pytest

import focus_project as fp
from focus_project import _interview, _milestones
from focus_project._errors import RegistryError
from focus_project.tests.helpers import SAT1, START, TEST_AT, TEST_DAY, at, make

if TYPE_CHECKING:
    from pathlib import Path

LIVE_ROW = {
    "id": "hackerrank-prep",
    "name": "HackerRank prep",
    "start": "2026-11-02",
    "end": "2026-11-05",
    "replaces": ["leetcode", "reading", "tutor"],
    "daily_minutes": 120,
    "unlock_minutes": 30,
    "subjects": ["a"],
    "site_patterns": ["leetcode.com"],
    "ended_on": None,
    "created_ms": 1793603609345,
    "work_url": "https://www.hackerrank.com/dashboard",
    "history": [],
}


def test_live_projects_json_shape_loads(data: Path) -> None:
    data.mkdir()
    (data / "projects.json").write_text(json.dumps({"projects": [LIVE_ROW]}))
    [p] = fp.list_projects()
    assert p.kind == "focus"
    assert p.test_at is None
    assert p.trips == ()
    assert p.weekend_answers == ()
    assert p.daily_on(date(2026, 11, 3)) == 120
    snap = fp.status(date(2026, 11, 3))
    assert snap["milestones"] == []
    assert snap["missed"] is False


def test_focus_row_stays_free_of_interview_keys(data: Path) -> None:
    fp.create_project(
        "f",
        name="F",
        start=START,
        end=TEST_DAY,
        replaces=["leetcode"],
        daily_minutes=30,
        unlock_minutes=10,
    )
    row = json.loads((data / "projects.json").read_text())["projects"][0]
    assert row["kind"] == "focus"
    assert not {"test_at", "invite_url", "trips", "weekend_answers"} & set(row)


def test_interview_roundtrip_and_file_shape(data: Path) -> None:
    p = make(
        trips=[fp.Trip(date(2026, 11, 20), date(2026, 11, 22))],
        weekend_answers={SAT1: False},
    )
    [back] = fp.list_projects()
    assert back == p
    assert back.kind == "interview"
    assert back.test_at == TEST_AT
    assert back.trips[0].entered_ms > 0
    row = json.loads((data / "projects.json").read_text())["projects"][0]
    assert row["test_at"] == "2026-11-27T10:00:00"
    assert row["trips"][0]["start"] == "2026-11-20"
    assert row["weekend_answers"] == {"2026-11-14": False}
    assert row["invite_url"].startswith("https://")


@pytest.mark.parametrize(
    "bad",
    [
        {"test_at": None},
        {"test_at": at(26, 10)},  # end != test day
        {"test_at": at(9, 10), "end": date(2026, 11, 9)},
        {"invite_url": "ftp://x.example/t"},
        {"invite_url": "javascript:alert(1)"},
        {"invite_url": "https://a b.example"},
        {"kind": "bogus"},
        {"trips": [fp.Trip(date(2026, 11, 28), date(2026, 11, 29))]},
        {"trips": [fp.Trip(date(2026, 11, 20), date(2026, 11, 19))]},
        {"weekend_answers": {date(2026, 11, 15): True}},  # a Sunday
        {"weekend_answers": {date(2026, 11, 28): True}},  # after T
        {"daily_minutes": 29},
    ],
)
def test_interview_validation(bad: dict[str, object]) -> None:
    with pytest.raises(ValueError):  # noqa: PT011
        make(**bad)


def test_focus_kind_rejects_interview_fields() -> None:
    with pytest.raises(ValueError, match="interview"):
        make(kind="focus")


def test_empty_invite_url_is_allowed() -> None:
    assert make(invite_url="").invite_url == ""


def test_budget_30_weekdays_120_weekend() -> None:
    p = make(unlock_minutes=60)
    assert p.daily_on(date(2026, 11, 10)) == 30  # Tue
    assert p.daily_on(date(2026, 11, 13)) == 30  # Fri
    assert p.daily_on(SAT1) == 120
    assert p.daily_on(date(2026, 11, 15)) == 120  # Sun
    assert p.unlock_on(date(2026, 11, 10)) == 30  # clamped to the day's target
    assert p.unlock_on(SAT1) == 60


def test_budget_flows_through_status() -> None:
    make()
    assert fp.status(date(2026, 11, 10))["daily_minutes"] == 30
    assert fp.status(SAT1)["daily_minutes"] == 120


def test_interview_exempt_from_floor_but_focus_is_not() -> None:
    make(daily_minutes=30, unlock_minutes=30)  # 3 gates, floor 90
    with pytest.raises(ValueError, match="at least"):
        fp.create_project(
            "f",
            name="F",
            start=date(2026, 12, 1),
            end=date(2026, 12, 2),
            replaces=["leetcode", "reading"],
            daily_minutes=30,
            unlock_minutes=10,
        )


def test_non_interview_has_no_weekends() -> None:
    focus = fp.create_project(
        "f",
        name="F",
        start=START,
        end=TEST_DAY,
        replaces=["leetcode"],
        daily_minutes=30,
        unlock_minutes=10,
    )
    assert _interview.saturdays(focus) == []


def test_trip_without_entry_time_uses_the_nominal_due() -> None:
    assert _milestones._trip_due(date(2026, 11, 13), 0) == at(12, 12)


def test_non_boolean_weekend_answer_is_a_bad_row(data: Path) -> None:
    make()
    path = data / "projects.json"
    rows = json.loads(path.read_text())
    rows["projects"][0]["weekend_answers"] = {"2026-11-14": "false"}
    path.write_text(json.dumps(rows))
    with pytest.raises(RegistryError):
        fp.list_projects()


def test_interview_unlock_edit_keeps_the_ratchet() -> None:
    make(unlock_minutes=60)
    fp.update_project("iv", today=SAT1, unlock_minutes=10)
    assert fp.list_projects()[0].unlock_on(SAT1) == 60  # lower holds from tomorrow
    assert fp.list_projects()[0].unlock_on(date(2026, 11, 15)) == 10
