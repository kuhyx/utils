# Copyright (c) 2026 Krzysztof Rudnicki
"""0.8.0: a tutor heartbeat chains the timer segment like a checkin."""

from __future__ import annotations

from focus_project import minutes
from focus_project.tests.test_minutes import D1, at, events, project


def test_tutor_heartbeat_keeps_the_segment_alive() -> None:
    """0.8.0: a tutor heartbeat is a beat of the open segment, like a checkin."""
    project()
    events(
        ("timer", "start", at(9)),
        ("tutor", "heartbeat", at(9, 7)),
        ("timer", "stop", at(9, 12)),
    )
    assert minutes.minutes_for(D1) == 12


def test_late_tutor_heartbeat_ends_the_segment_at_the_last_beat() -> None:
    project()
    events(
        ("timer", "start", at(9)),
        ("tutor", "heartbeat", at(9, 11)),  # 11 min > 600 s: segment ends at 9:00
        ("timer", "stop", at(9, 13)),  # nothing open: ignored
    )
    assert minutes.minutes_for(D1) == 5  # only the heartbeat's own [9:06, 9:11]


def test_tutor_heartbeat_never_opens_a_segment() -> None:
    project()
    events(
        ("tutor", "heartbeat", at(9)),
        ("timer", "stop", at(9, 4)),
    )
    assert minutes.minutes_for(D1) == 5


def test_other_heartbeats_never_chain_the_timer() -> None:
    project()
    events(
        ("timer", "start", at(9)),
        ("sql_drills", "heartbeat", at(9, 7)),
        ("timer", "stop", at(9, 12)),
    )
    assert minutes.minutes_for(D1) == 5  # [9:02, 9:07] only


def test_tutor_heartbeats_chain_with_checkins() -> None:
    project()
    events(
        ("timer", "start", at(9)),
        ("tutor", "heartbeat", at(9, 7)),
        ("timer", "checkin", at(9, 14)),
        ("tutor", "heartbeat", at(9, 21)),
        ("timer", "stop", at(9, 25)),
    )
    assert minutes.minutes_for(D1) == 25
