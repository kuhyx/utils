# Copyright (c) 2026 Krzysztof Rudnicki
"""The mock milestone: a score counts only after a >= 90 min focus session."""

from __future__ import annotations

import focus_project as fp
from focus_project.tests.helpers import at, make, session, states


def test_mock_needs_a_score_after_a_long_session() -> None:
    p = make()
    assert states(p, at(26, 8))["mock"] == "missed"
    session(at(25, 20), 90)
    fp.record_evidence("iv", "mock", "score", 64, now=at(26, 8))
    assert states(fp.list_projects()[0], at(26, 9))["mock"] == "late_done"


def test_score_without_a_session_does_not_complete_mock() -> None:
    p = make()
    fp.record_evidence("iv", "mock", "score", 64, now=at(24, 9))
    assert states(p, at(24, 10))["mock"] == "pending"
    assert states(p, at(26, 8))["mock"] == "missed"
    assert fp.owed_lock(at(26, 8)) is not None


def test_short_session_does_not_complete_mock() -> None:
    p = make()
    session(at(24, 7), 89)
    fp.record_evidence("iv", "mock", "score", 64, now=at(24, 9))
    assert states(p, at(24, 10))["mock"] == "pending"


def test_session_broken_by_a_gap_does_not_complete_mock() -> None:
    p = make()
    session(at(24, 6), 60)  # 06:00-07:00, then an 11 min hole (> 600 s)
    session(at(24, 7, 11), 60)
    fp.record_evidence("iv", "mock", "score", 64, now=at(24, 9))
    assert states(p, at(24, 10))["mock"] == "pending"


def test_session_must_end_before_the_score() -> None:
    p = make()
    session(at(24, 8), 90)  # ends 09:30
    fp.record_evidence("iv", "mock", "score", 64, now=at(24, 9))
    assert states(p, at(24, 10))["mock"] == "pending"
    fp.record_evidence("iv", "mock", "score", 66, now=at(24, 9, 30))
    assert states(p, at(24, 10))["mock"] == "done"  # ends exactly at the score


def test_other_projects_sessions_do_not_count() -> None:
    p = make()
    session(at(24, 7), 90, pid="other")
    fp.record_evidence("iv", "mock", "score", 64, now=at(24, 9))
    assert states(p, at(24, 10))["mock"] == "pending"


def test_session_on_time_but_score_late_is_late_done() -> None:
    p = make()
    session(at(25, 20), 100)
    fp.record_evidence("iv", "mock", "score", 64, now=at(26, 0, 5))
    assert states(p, at(26, 1))["mock"] == "late_done"
