# Copyright (c) 2026 Krzysztof Rudnicki
"""The leisure budget (0.14.0): base 7 h, cap 10 h from ``LEISURE_FROM``."""

from __future__ import annotations

from datetime import date, timedelta

from earned_time import (
    GAMING_BASE_MINUTES,
    GAMING_CEILING_MINUTES,
    LEISURE_FROM,
    TUTOR_EARNERS,
    UNIFIED_FROM,
    base_for,
    gaming_base_minutes_for,
    gaming_ceiling_minutes_for,
    resolve,
)

EVE = LEISURE_FROM - timedelta(days=1)
FULL = {"workout": 1, "leetcode": 1, "reading": 1, "tutor": 60}
NONE = dict.fromkeys(FULL, 0)


def _gaming(day: date, answers: dict[str, int], *, leisure: bool = False) -> int:
    return resolve(answers, day, TUTOR_EARNERS, leisure=leisure).gaming_minutes


def test_parked_until_phase_two() -> None:
    assert date(2027, 1, 1) == LEISURE_FROM


def test_base_and_ceiling_switch_on_leisure_from() -> None:
    assert gaming_base_minutes_for(EVE) == GAMING_BASE_MINUTES == 5 * 60
    assert gaming_base_minutes_for(LEISURE_FROM) == 7 * 60
    assert gaming_ceiling_minutes_for(EVE) == GAMING_CEILING_MINUTES == 8 * 60
    assert gaming_ceiling_minutes_for(LEISURE_FROM) == 10 * 60


def test_enforced_days_before_leisure_from_are_unchanged() -> None:
    for day in (UNIFIED_FROM, EVE):
        assert base_for(day).gaming_minutes == 180
        assert _gaming(day, NONE) == 180
        assert _gaming(day, FULL) == 180 + 300 == 480
        assert _gaming(day, FULL, leisure=False) == 480


def test_leisure_prices_an_old_day_as_the_shadow_budget() -> None:
    assert base_for(UNIFIED_FROM, leisure=True).gaming_minutes == 300
    assert _gaming(UNIFIED_FROM, NONE, leisure=True) == 300
    assert _gaming(UNIFIED_FROM, FULL, leisure=True) == 300 + 300 == 600


def test_from_leisure_from_the_flag_changes_nothing() -> None:
    assert _gaming(LEISURE_FROM, NONE) == 300
    assert _gaming(LEISURE_FROM, FULL) == 600
    assert _gaming(LEISURE_FROM, FULL, leisure=True) == 600


def test_leisure_never_moves_shutdown_or_the_sick_rule() -> None:
    for sick in (False, True):
        for answers in (NONE, FULL, {**NONE, "leetcode": 1, "reading": 1}):
            plain = resolve(answers, UNIFIED_FROM, TUTOR_EARNERS, sick=sick)
            shadow = resolve(
                answers, UNIFIED_FROM, TUTOR_EARNERS, sick=sick, leisure=True
            )
            assert shadow.shutdown_minutes == plain.shutdown_minutes
            assert shadow.sick_lift_minutes == plain.sick_lift_minutes
            assert shadow.terms == plain.terms
            assert shadow.base.shutdown_minutes == plain.base.shutdown_minutes
