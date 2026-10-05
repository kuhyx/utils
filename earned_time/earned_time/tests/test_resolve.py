# Copyright (c) 2026 Krzysztof Rudnicki
"""The one sum: base, terms, ceilings, and failing closed."""

from __future__ import annotations

from datetime import date
import logging

import pytest

from earned_time import Earner, base_for, resolve

BEFORE_CUT = date(2026, 9, 30)
AFTER_CUT = date(2026, 10, 4)


def test_base_before_and_after_the_reading_cut() -> None:
    assert base_for(BEFORE_CUT).gaming_minutes == 300
    assert base_for(BEFORE_CUT).shutdown_minutes == 20 * 60
    assert base_for(AFTER_CUT).gaming_minutes == 240
    assert base_for(AFTER_CUT).shutdown_minutes == 19 * 60


def test_base_defaults_to_today() -> None:
    assert base_for().gaming_minutes in {240, 300}


def test_nothing_earned_is_the_base() -> None:
    day = resolve({"workout": 0, "leetcode": False, "reading": False}, AFTER_CUT)
    assert (day.gaming_minutes, day.shutdown_minutes) == (240, 19 * 60)


def test_terms_add_up() -> None:
    day = resolve({"workout": 1, "leetcode": True, "reading": False}, AFTER_CUT)
    assert day.gaming_minutes == 240 + 120 + 60
    assert day.shutdown_minutes == 19 * 60 + 120 + 60
    assert day.term("reading").answer == 0


def test_ceilings_hold() -> None:
    day = resolve({"workout": 5, "leetcode": True, "reading": True}, AFTER_CUT)
    assert (day.gaming_minutes, day.shutdown_minutes) == (8 * 60, 23 * 60)


def test_unknown_answer_earns_nothing_but_is_kept() -> None:
    day = resolve({"workout": None, "leetcode": True, "reading": True}, AFTER_CUT)
    assert day.term("workout").answer is None
    assert day.term("workout").gaming_minutes == 0


def test_negative_count_is_zero() -> None:
    day = resolve({"workout": -3, "leetcode": False, "reading": False}, AFTER_CUT)
    assert day.term("workout").answer == 0


def test_missing_answer_is_logged_and_earns_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        day = resolve({"leetcode": True}, AFTER_CUT)
    assert "No answer for the workout earner" in caplog.text
    assert day.term("workout").answer is None


def test_unregistered_name_raises() -> None:
    with pytest.raises(KeyError, match="anky"):
        resolve({"anky": True})


def test_term_lookup_unknown_raises() -> None:
    with pytest.raises(KeyError):
        resolve({}, AFTER_CUT).term("nope")


def test_new_penalised_earner_keeps_the_best_case() -> None:
    # A hypothetical next earner on top of the real registry (reading and
    # anki already penalised by 2026-10-11): 5h - 1h - 30m - 30m.
    piano = Earner(
        name="piano",
        label="piano",
        gaming_minutes=30,
        shutdown_minutes=30,
        penalty_from=date(2026, 10, 10),
    )
    from earned_time import EARNERS

    earners = (*EARNERS, piano)
    later = date(2026, 10, 11)
    assert base_for(later, earners).gaming_minutes == 180
    assert base_for(later, earners).shutdown_minutes == 18 * 60
    others = {"workout": 0, "leetcode": 0, "reading": 0, "anki": 0}
    skipped = resolve({**others, "piano": 0}, later, earners)
    done = resolve({**others, "piano": 1}, later, earners)
    assert done.gaming_minutes - skipped.gaming_minutes == 30
    assert done.shutdown_minutes == 18 * 60 + 30
