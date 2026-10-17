# Copyright (c) 2026 Krzysztof Rudnicki
"""The sick-day shutdown (0.13.0): 20:00 plus gaming pay, gaming untouched."""

from __future__ import annotations

from datetime import date

import pytest

from earned_time import (
    SICK_SHUTDOWN_FLOOR_MINUTES,
    resolve,
    shutdown_ceiling_for,
    sick_shutdown_from,
)

LADDER_DAY = date(2026, 10, 16)
PRE_LADDER_DAY = date(2026, 10, 4)

NOTHING: dict[str, int | bool | None] = {
    "workout": 0,
    "leetcode": False,
    "reading": False,
    "tutor": 0,
}
SOME: dict[str, int | bool | None] = {**NOTHING, "workout": 1, "leetcode": True}
EVERYTHING: dict[str, int | bool | None] = {
    "workout": 1,
    "leetcode": True,
    "reading": True,
    "tutor": 60,
}


def test_the_floor_is_eight_pm() -> None:
    assert SICK_SHUTDOWN_FLOOR_MINUTES == 20 * 60


def test_a_sick_day_that_earned_nothing_shuts_down_at_eight() -> None:
    normal = resolve(NOTHING, LADDER_DAY)
    sick = resolve(NOTHING, LADDER_DAY, sick=True)
    assert normal.shutdown_minutes == 18 * 60 + 50
    assert sick.shutdown_minutes == 20 * 60
    assert sick.sick
    assert sick.sick_lift_minutes == 70
    assert not normal.sick
    assert normal.sick_lift_minutes == 0


def test_earning_stacks_on_the_floor_at_gaming_pay() -> None:
    """0.13.0: 20:00 plus every term's gaming pay (LeetCode + reading = +2 h)."""
    answers = {**NOTHING, "leetcode": True, "reading": True}
    sick = resolve(answers, LADDER_DAY, sick=True)
    assert sick.shutdown_minutes == 22 * 60
    assert sick.shutdown_minutes == sick_shutdown_from(120, LADDER_DAY)
    some = resolve(SOME, LADDER_DAY, sick=True)  # workout 120 + LeetCode 60
    assert some.shutdown_minutes == 23 * 60


@pytest.mark.parametrize("answers", [NOTHING, SOME, EVERYTHING])
@pytest.mark.parametrize("day", [LADDER_DAY, PRE_LADDER_DAY])
def test_never_below_the_old_max_rule(
    answers: dict[str, int | bool | None], day: date
) -> None:
    """Raise-only against 0.11.0's max(20:00, earned), so it may land same-day."""
    if day == PRE_LADDER_DAY:
        answers = {k: v for k, v in answers.items() if k != "tutor"}
    normal = resolve(answers, day).shutdown_minutes
    old = min(shutdown_ceiling_for(day), max(20 * 60, normal))
    assert resolve(answers, day, sick=True).shutdown_minutes >= old


def test_a_fully_done_sick_day_still_stops_at_the_ceiling() -> None:
    sick = resolve(EVERYTHING, LADDER_DAY, sick=True)
    assert sick.shutdown_minutes == shutdown_ceiling_for(LADDER_DAY) == 23 * 60


def test_the_floor_applies_before_the_ladder_too() -> None:
    answers = {"workout": 0, "leetcode": False, "reading": False}
    normal = resolve(answers, PRE_LADDER_DAY)
    sick = resolve(answers, PRE_LADDER_DAY, sick=True)
    assert normal.shutdown_minutes == 19 * 60
    assert sick.shutdown_minutes == 20 * 60


@pytest.mark.parametrize("answers", [NOTHING, SOME, EVERYTHING])
def test_gaming_and_every_term_are_unchanged(
    answers: dict[str, int | bool | None],
) -> None:
    normal = resolve(answers, LADDER_DAY)
    sick = resolve(answers, LADDER_DAY, sick=True)
    assert sick.gaming_minutes == normal.gaming_minutes
    assert sick.terms == normal.terms
    assert sick.base == normal.base


def test_the_helper_is_capped_at_the_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    assert sick_shutdown_from(0, LADDER_DAY) == 20 * 60
    assert sick_shutdown_from(60, LADDER_DAY) == 21 * 60
    assert sick_shutdown_from(600, LADDER_DAY) == 23 * 60
    monkeypatch.setattr(
        "earned_time._sick.shutdown_ceiling_for", lambda _day: 19 * 60 + 30
    )
    assert sick_shutdown_from(0, LADDER_DAY) == 19 * 60 + 30
