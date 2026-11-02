# Copyright (c) 2026 Krzysztof Rudnicki
"""minutes_for: union of intervals, gap rule, cap, project filter."""

from __future__ import annotations

from datetime import date, datetime
import json
from typing import TYPE_CHECKING

import focus_project as fp
from focus_project import _clock, minutes
from focus_project._paths import activity_path

if TYPE_CHECKING:
    import pytest

D1 = date(2026, 11, 2)


def at(hour: int, minute: int = 0, second: int = 0, day: date = D1) -> float:
    """Local unix time on ``day``."""
    return (
        datetime(day.year, day.month, day.day, hour, minute, second)
        .astimezone()
        .timestamp()
    )


def project(daily: int = 120) -> None:
    fp.create_project(
        "hr",
        name="HR prep",
        start=D1,
        end=date(2026, 11, 5),
        replaces=["leetcode"],
        daily_minutes=daily,
        unlock_minutes=min(30, daily),
        site_patterns=["leetcode.com"],
    )


def events(*rows: tuple[str, str, float]) -> None:
    activity_path().parent.mkdir(parents=True, exist_ok=True)
    with activity_path().open("a", encoding="utf-8") as handle:
        for source, kind, ts in rows:
            row = {
                "ts": ts,
                "source": source,
                "kind": kind,
                "project": "hr",
                "dev": "pc",
            }
            handle.write(json.dumps(row) + "\n")


def test_no_project_is_zero() -> None:
    events(("timer", "start", at(9)), ("timer", "stop", at(9, 5)))
    assert minutes.minutes_for(D1) == 0


def test_timer_start_checkin_stop() -> None:
    project()
    events(
        ("timer", "start", at(9)),
        ("timer", "checkin", at(9, 5)),
        ("timer", "checkin", at(9, 10)),
        ("timer", "stop", at(9, 12)),
    )
    assert minutes.minutes_for(D1) == 12


def test_missed_checkin_stops_the_segment() -> None:
    project()
    events(
        ("timer", "start", at(9)),
        ("timer", "checkin", at(9, 5)),
        ("timer", "checkin", at(9, 30)),  # 25 min gap > 600 s: not credited
        ("timer", "stop", at(9, 33)),
    )
    assert minutes.minutes_for(D1) == 5 + 3


def test_gap_of_exactly_600s_counts() -> None:
    project()
    events(("timer", "start", at(9)), ("timer", "checkin", at(9, 10)))
    assert minutes.minutes_for(D1) == 10


def test_open_timer_credits_only_up_to_last_checkin() -> None:
    project()
    events(("timer", "start", at(9)), ("timer", "checkin", at(9, 4)))
    assert minutes.minutes_for(D1) == 4


def test_stop_without_open_segment_ignored() -> None:
    project()
    events(
        ("timer", "stop", at(9)),
        ("timer", "start", at(10)),
        ("timer", "stop", at(10, 2)),
    )
    assert minutes.minutes_for(D1) == 2


def test_start_while_open_acts_as_checkin() -> None:
    project()
    events(
        ("timer", "start", at(9)),
        ("timer", "start", at(9, 3)),
        ("timer", "stop", at(9, 5)),
    )
    assert minutes.minutes_for(D1) == 5


def test_heartbeat_covers_five_minutes() -> None:
    project()
    events(("sql_drills", "heartbeat", at(11)))
    assert minutes.minutes_for(D1) == 5


def test_overlaps_never_double_count() -> None:
    project()
    events(
        ("timer", "start", at(9)),
        ("timer", "stop", at(9, 6)),
        ("tutor", "heartbeat", at(9, 5)),  # [9:00, 9:05] inside the timer span
        ("sql_drills", "heartbeat", at(9, 8)),  # [9:03, 9:08] extends it by 2
    )
    assert minutes.minutes_for(D1) == 8


def test_capped_at_daily_minutes() -> None:
    project(daily=30)
    events(
        *(("tutor", "heartbeat", at(9, 5 * k)) for k in range(1, 9)),
        ("tutor", "heartbeat", at(12)),
    )
    assert minutes.minutes_for(D1) == 30


def test_other_day_and_other_project_events_ignored() -> None:
    project()
    events(("tutor", "heartbeat", at(11, day=date(2026, 11, 3))))
    with activity_path().open("a", encoding="utf-8") as handle:
        row = {"ts": at(11), "source": "tutor", "kind": "heartbeat", "project": "x"}
        handle.write(json.dumps(row) + "\n")
        row = {"ts": at(12), "source": "tutor", "kind": "heartbeat", "project": None}
        handle.write(json.dumps(row) + "\n")
    assert minutes.minutes_for(D1) == 0


def test_garbage_lines_skipped() -> None:
    project()
    events(("tutor", "heartbeat", at(11)))
    with activity_path().open("a", encoding="utf-8") as handle:
        handle.write(
            "not json\n[1]\n" + json.dumps({"ts": "x", "project": "hr"}) + "\n\n"
        )
        handle.write(
            json.dumps({"ts": at(12), "source": "tutor", "project": "hr"}) + "\n"
        )
    assert minutes.minutes_for(D1) == 5 + 5


def test_interval_spanning_midnight_is_clipped() -> None:
    project()
    events(("tutor", "heartbeat", at(0, 2)))  # covers 23:57..00:02 of D1
    assert minutes.minutes_for(D1) == 2
    assert minutes.minutes_for(date(2026, 11, 1)) == 0  # no project there


def test_broken_registry_reads_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    from focus_project import _api, _errors

    def boom(_day: date) -> None:
        msg = "corrupt"
        raise _errors.RegistryError(msg)

    monkeypatch.setattr(_api, "active", boom)
    assert minutes.minutes_for(D1) == 0


def test_missing_activity_file_is_zero() -> None:
    project()
    assert minutes.minutes_for(D1) == 0


def test_contained_heartbeat_adds_nothing() -> None:
    project()
    events(
        ("timer", "start", at(9)),
        ("timer", "stop", at(9, 10)),
        ("tutor", "heartbeat", at(9, 8)),
    )
    assert minutes.minutes_for(D1) == 10


def test_non_timer_kinds_from_timer_source_ignored() -> None:
    project()
    events(("timer", "heartbeat", at(9)))
    assert minutes.minutes_for(D1) == 0


def _timer_run(start: float, checkins: int) -> None:
    events(
        ("timer", "start", start),
        *(("timer", "checkin", start + i * 420) for i in range(1, checkins + 1)),
        ("timer", "stop", start + checkins * 420 + 60),
    )


def test_events_ahead_of_the_clock_earn_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A phone clock 3 h fast must not pay before the work happens."""
    project()
    _timer_run(at(11), 17)  # 119 min of "work", all after the real 08:00
    monkeypatch.setattr(_clock, "now", lambda: at(8))
    assert minutes.minutes_for(D1) == 0


def test_an_interval_straddling_now_counts_only_up_to_now(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project()
    _timer_run(at(11), 17)
    monkeypatch.setattr(_clock, "now", lambda: at(11, 30))
    assert minutes.minutes_for(D1) == 30
    monkeypatch.setattr(_clock, "now", lambda: at(12, 0))
    assert minutes.minutes_for(D1) == 60


def test_a_heartbeat_ahead_of_now_is_clipped(monkeypatch: pytest.MonkeyPatch) -> None:
    project()
    events(("tutor", "heartbeat", at(12, 2)))  # vouches for 11:57..12:02
    monkeypatch.setattr(_clock, "now", lambda: at(12, 0))
    assert minutes.minutes_for(D1) == 3


def test_an_explicit_now_overrides_the_clock() -> None:
    project()
    _timer_run(at(11), 17)
    assert minutes.minutes_for(D1, now=at(11, 10)) == 10
    assert minutes.minutes_for(D1) == 120  # the pinned 2030 clock: all past
