# Copyright (c) 2026 Krzysztof Rudnicki
"""update_project: same validation as create, no rewriting of the past."""

from __future__ import annotations

from datetime import date, timedelta
import json
from typing import TYPE_CHECKING

import pytest

import focus_project as fp

if TYPE_CHECKING:
    from pathlib import Path

D1 = date(2026, 11, 2)
D4 = date(2026, 11, 5)
DAY = timedelta(days=1)


def _make(pid: str = "hr", start: date = D1, end: date = D4) -> fp.Project:
    return fp.create_project(
        pid,
        name="HackerRank prep",
        start=start,
        end=end,
        replaces=["leetcode", "reading"],
        daily_minutes=120,
        unlock_minutes=30,
    )


def test_update_changes_fields_and_normalizes() -> None:
    _make()
    got = fp.update_project(
        "hr",
        today=D1,
        name="Interview",
        end=D4 + DAY,
        replaces=["book", "tutor", "book"],
        subjects=["a"],
        site_patterns=["x.com"],
    )
    assert fp.list_projects() == [got]
    assert got.name == "Interview"
    assert got.end == D4 + DAY
    assert got.replaces == ("reading", "tutor")
    assert got.subjects == ("a",)
    assert got.site_patterns == ("x.com",)
    assert got.created_ms == fp.list_projects()[0].created_ms


def test_update_nothing_is_a_noop() -> None:
    before = _make()
    assert fp.update_project("hr", today=D1) == before


def test_update_defaults_today_to_real_today() -> None:
    now = date.today()  # noqa: DTZ011
    _make("now", start=now, end=now + DAY)
    assert fp.update_project("now", name="X").name == "X"


def test_unknown_id_and_field() -> None:
    _make()
    with pytest.raises(KeyError):
        fp.update_project("nope", today=D1, name="x")
    with pytest.raises(ValueError, match="cannot change"):
        fp.update_project("hr", today=D1, ended_on=D4)


@pytest.mark.parametrize(
    ("kw", "match"),
    [
        ({"name": " "}, "name"),
        ({"end": D1 - DAY}, "end"),
        ({"replaces": ["workout"]}, "gate"),
        ({"replaces": []}, "replace"),
        ({"daily_minutes": 0}, "daily_minutes"),
        ({"unlock_minutes": 121}, "unlock_minutes"),
        ({"daily_minutes": 20}, "unlock_minutes"),
    ],
)
def test_update_validation(kw: dict[str, object], match: str) -> None:
    before = _make()
    with pytest.raises(ValueError, match=match):
        fp.update_project("hr", today=D1, **kw)
    assert fp.list_projects() == [before]


def test_update_overlap_rejected_self_is_not_overlap() -> None:
    _make()
    _make("next", start=D4 + DAY, end=D4 + 3 * DAY)
    with pytest.raises(ValueError, match="overlap"):
        fp.update_project("hr", today=D1, end=D4 + DAY)
    fp.update_project("hr", today=D1, end=D4)  # own range is fine
    assert fp.update_project("hr", today=D1, start=D1, end=D4).end == D4


def test_past_start_refused_future_start_editable() -> None:
    _make()
    with pytest.raises(ValueError, match="start"):
        fp.update_project("hr", today=D1 + DAY, start=D1 + 2 * DAY)
    assert fp.update_project("hr", today=D1 + DAY, start=D1).start == D1
    fp.update_project("hr", today=D1 - DAY, start=D1 + DAY)
    assert fp.list_projects()[0].start == D1 + DAY
    with pytest.raises(ValueError, match="start"):
        fp.update_project("hr", today=D1, start=D1 - 2 * DAY)


def test_ended_and_finished_projects_refused() -> None:
    _make()
    with pytest.raises(ValueError, match="over"):
        fp.update_project("hr", today=D4 + DAY, name="late")
    fp.end_project("hr", date(2031, 1, 1))
    with pytest.raises(ValueError, match="ended"):
        fp.update_project("hr", today=D1, name="x")


def test_end_in_the_past_refused() -> None:
    _make()
    with pytest.raises(ValueError, match="past"):
        fp.update_project("hr", today=D1 + 2 * DAY, end=D1 + DAY)


def test_daily_cut_applies_from_tomorrow(data: Path) -> None:
    _make()
    fp.update_project("hr", today=D1 + 2 * DAY, daily_minutes=60, unlock_minutes=10)
    p = fp.list_projects()[0]
    assert (p.daily_minutes, p.unlock_minutes) == (60, 10)
    assert p.daily_on(D1 + DAY) == 120
    assert p.daily_on(D1 + 2 * DAY) == 120  # today keeps its targets
    assert p.unlock_on(D1 + 2 * DAY) == 30
    assert p.daily_on(D4) == 60
    assert p.unlock_on(D4) == 10
    # a deeper cut the same day keeps the one preserved row, a later day adds one
    fp.update_project("hr", today=D1 + 2 * DAY, daily_minutes=90)
    assert len(fp.list_projects()[0].history) == 1
    fp.update_project("hr", today=D4, daily_minutes=45, unlock_minutes=5)
    p = fp.list_projects()[0]
    assert [h.until for h in p.history] == [D1 + 2 * DAY, D4]
    assert p.daily_on(D4) == 90
    assert p.daily_on(D4 + DAY) == 45
    raw = json.loads((data / "projects.json").read_text())["projects"][0]
    assert raw["history"][0] == {
        "until": "2026-11-04",
        "daily_minutes": 120,
        "unlock_minutes": 30,
        "replaces": ["leetcode", "reading"],
    }


def test_future_project_daily_change_keeps_no_history() -> None:
    _make()
    fp.update_project("hr", today=D1 - DAY, daily_minutes=60, unlock_minutes=10)
    p = fp.list_projects()[0]
    assert p.history == ()
    assert p.daily_on(D1) == 60
    # on the first day a cut waits for tomorrow, like any started project
    fp.update_project("hr", today=D1, daily_minutes=50)
    p = fp.list_projects()[0]
    assert p.daily_on(D1) == 60
    assert p.daily_on(D1 + DAY) == 50


def test_same_value_edit_adds_no_history() -> None:
    _make()
    fp.update_project("hr", today=D1 + DAY, daily_minutes=120, name="n")
    assert fp.list_projects()[0].history == ()


def test_status_and_minutes_use_the_day_values(tmp_path: Path) -> None:
    _make()
    fp.update_project("hr", today=D1 + DAY, daily_minutes=60, unlock_minutes=10)
    assert fp.status(D1)["daily_minutes"] == 120
    assert fp.status(D1)["unlock_minutes"] == 30
    assert fp.status(D1 + DAY)["daily_minutes"] == 120
    assert fp.status(D1 + 2 * DAY)["daily_minutes"] == 60


def test_work_url_is_editable_kept_and_clearable() -> None:
    _make()
    url = "https://www.hackerrank.com/dashboard"
    assert fp.update_project("hr", today=D1, work_url=url).work_url == url
    assert fp.update_project("hr", today=D1, name="Other").work_url == url
    assert fp.update_project("hr", today=D1, work_url="").work_url == ""


def test_update_refuses_a_non_http_work_url() -> None:
    _make()
    with pytest.raises(ValueError, match="work_url"):
        fp.update_project("hr", today=D1, work_url="javascript:alert(1)")
