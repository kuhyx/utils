# Copyright (c) 2026 Krzysztof Rudnicki
"""The gap-day waiver: Anki and the old Automation, from ANKI_WAIVED_FROM."""

from __future__ import annotations

from datetime import timedelta

import pytest

from earned_time import (
    ANKI_WAIVED_FROM,
    EARNERS,
    LADDER_FROM,
    TUTOR_EARNERS,
    TUTOR_FROM,
    earners_for,
    resolve,
)

BEFORE = ANKI_WAIVED_FROM - timedelta(days=1)
NAMES = ("workout", "leetcode", "reading", "anki", "automation")


def test_the_waiver_sits_between_the_old_registry_and_the_tutor() -> None:
    assert BEFORE < ANKI_WAIVED_FROM < TUTOR_FROM
    assert earners_for(BEFORE) is EARNERS
    assert [e.name for e in earners_for(ANKI_WAIVED_FROM)] == list(NAMES[:3])
    assert earners_for(TUTOR_FROM) is TUTOR_EARNERS


def test_nothing_done_is_raised_by_exactly_what_the_two_paid() -> None:
    zero = dict.fromkeys(NAMES, 0)
    # TUTOR_FROM == LADDER_FROM: the waiver's only day is pre-ladder; the first
    # ladder day's floor is in test_maturity_floor.py.
    assert ANKI_WAIVED_FROM < LADDER_FROM == TUTOR_FROM
    gap = resolve(zero, ANKI_WAIVED_FROM)
    unwaived = resolve(zero, ANKI_WAIVED_FROM, EARNERS)
    assert (gap.base.gaming_minutes, gap.gaming_minutes) == (240, 240)
    assert gap.shutdown_minutes == 19 * 60  # 20:00 minus reading's 60
    assert gap.gaming_minutes - unwaived.gaming_minutes == 30 + 30
    assert gap.shutdown_minutes - unwaived.shutdown_minutes == 30 + 30


@pytest.mark.parametrize("workout", [0, 1])
@pytest.mark.parametrize("leetcode", [0, 1])
@pytest.mark.parametrize("reading", [0, 1])
@pytest.mark.parametrize("anki", [0, 1])
def test_raise_only_on_every_combination(
    workout: int, leetcode: int, reading: int, anki: int
) -> None:
    answers = {
        "workout": workout,
        "leetcode": leetcode,
        "reading": reading,
        "anki": anki,
        "automation": anki,
    }
    day = ANKI_WAIVED_FROM
    waived = resolve(answers, day)
    unwaived = resolve(answers, day, EARNERS)
    assert waived.gaming_minutes >= unwaived.gaming_minutes
    assert waived.shutdown_minutes >= unwaived.shutdown_minutes
    if anki:
        assert waived.gaming_minutes == unwaived.gaming_minutes
        assert waived.shutdown_minutes == unwaived.shutdown_minutes


def test_all_done_still_8h_and_23() -> None:
    done = resolve(dict.fromkeys(NAMES, 1), ANKI_WAIVED_FROM)
    assert (done.gaming_minutes, done.shutdown_minutes) == (480, 23 * 60)
