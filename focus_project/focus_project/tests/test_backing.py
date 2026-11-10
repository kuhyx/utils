# Copyright (c) 2026 Krzysztof Rudnicki
"""0.10.0: a timer span earns only if a same-project beat backs it."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import focus_project as fp
from focus_project import _api, minutes
from focus_project.sources import activity
from focus_project.tests import test_minutes as tm

if TYPE_CHECKING:
    import pytest

DAY = date(2026, 11, 8)  # BACKING_FROM


def at(hour: int, minute: int = 0) -> float:
    return tm.at(hour, minute, day=DAY)


def proj() -> None:
    fp.create_project(
        "hr",
        name="HR prep",
        start=DAY,
        end=date(2026, 11, 12),
        replaces=["leetcode"],
        daily_minutes=120,
        unlock_minutes=30,
        site_patterns=["leetcode.com"],
    )


def rows(*items: tuple[str, str, float]) -> None:
    tm.events(*items)


def timer_only() -> None:
    rows(
        ("timer", "start", at(9)),
        ("timer", "checkin", at(9, 5)),
        ("timer", "stop", at(9, 10)),
    )


def test_timer_only_stretch_pays_zero_and_shows_unbacked() -> None:
    proj()
    timer_only()
    assert minutes.minutes_for(DAY) == 0
    assert minutes.unbacked_minutes_for(DAY) == 10
    assert fp.status(DAY)["unbacked_minutes"] == 10


def test_a_beat_in_the_span_backs_all_of_it() -> None:
    proj()
    timer_only()
    rows(("sql_drills", "heartbeat", at(9, 5)))
    assert minutes.unbacked_minutes_for(DAY) == 0
    assert minutes.minutes_for(DAY) == 10


def test_a_beat_backs_only_the_spans_it_touches() -> None:
    proj()
    timer_only()
    rows(("sql_drills", "heartbeat", at(9, 7)))
    # 9:00-9:05 stays unbacked, but the beat itself pays 9:02-9:07.
    assert minutes.unbacked_minutes_for(DAY) == 2


def test_a_beat_at_the_end_of_the_span_backs_it() -> None:
    proj()
    rows(
        ("timer", "start", at(9)),
        ("timer", "stop", at(9, 10)),
        ("sql_drills", "heartbeat", at(9, 10)),
    )
    assert minutes.unbacked_minutes_for(DAY) == 0
    assert minutes.minutes_for(DAY) == 10


def test_a_beat_just_before_the_span_backs_it() -> None:
    proj()
    rows(
        ("sql_drills", "heartbeat", at(8, 56)),  # within 300 s before 9:00
        ("timer", "start", at(9)),
        ("timer", "stop", at(9, 5)),
    )
    assert minutes.unbacked_minutes_for(DAY) == 0


def test_a_late_beat_does_not_back_it() -> None:
    proj()
    timer_only()
    rows(("sql_drills", "heartbeat", at(9, 40)))
    assert minutes.unbacked_minutes_for(DAY) == 10


def test_beats_up_to_twenty_minutes_apart_bridge_the_span() -> None:
    proj()
    rows(
        ("tutor", "heartbeat", at(8, 50)),
        ("timer", "start", at(9)),
        ("timer", "checkin", at(9, 5)),
        ("timer", "stop", at(9, 8)),
        ("tutor", "heartbeat", at(9, 10)),
    )
    assert minutes.unbacked_minutes_for(DAY) == 0


def test_beats_over_twenty_minutes_apart_do_not_bridge() -> None:
    proj()
    rows(
        ("tutor", "heartbeat", at(8, 30)),
        ("timer", "start", at(9)),
        ("timer", "stop", at(9, 8)),
        ("tutor", "heartbeat", at(9, 40)),
    )
    assert minutes.unbacked_minutes_for(DAY) == 8


def test_browser_never_backs() -> None:
    proj()
    timer_only()
    rows(("browser", "heartbeat", at(9, 7)))
    # The beat pays its own 9:02-9:07 but backs no timer span.
    assert minutes.unbacked_minutes_for(DAY) == 5
    assert minutes.minutes_for(DAY) == 5


def test_days_before_backing_from_keep_the_old_rule() -> None:
    fp.create_project(
        "hr",
        name="Old",
        start=date(2026, 11, 2),
        end=date(2026, 11, 5),
        replaces=["leetcode"],
        daily_minutes=120,
        unlock_minutes=30,
        site_patterns=["leetcode.com"],
    )
    old = date(2026, 11, 2)
    rows(("timer", "start", tm.at(9)), ("timer", "stop", tm.at(9, 10)))
    assert minutes.minutes_for(old) == 10
    assert minutes.unbacked_minutes_for(old) == 0


def test_no_project_is_zero_unbacked() -> None:
    assert minutes.unbacked_minutes_for(DAY) == 0
    assert fp.status(DAY)["unbacked_minutes"] == 0


def test_unbacked_is_clipped_at_now() -> None:
    proj()
    timer_only()
    assert minutes.unbacked_minutes_for(DAY, now=at(9, 4)) == 4


def test_split_timer_returns_backed_and_unbacked() -> None:
    proj()
    timer_only()
    project = _api.active(DAY)
    assert project is not None
    backed, unbacked = activity.split_timer(DAY, project)
    assert backed == []
    assert unbacked == [(at(9), at(9, 5)), (at(9, 5), at(9, 10))]


def test_backing_from_is_exported() -> None:
    assert date(2026, 11, 8) == fp.BACKING_FROM
    assert fp.unbacked_minutes_for is minutes.unbacked_minutes_for


def test_registry_error_reads_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_day: date) -> None:
        raise OSError

    monkeypatch.setattr("focus_project._api.active", boom)
    assert minutes.unbacked_minutes_for(DAY) == 0
