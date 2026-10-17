# Copyright (c) 2026 Krzysztof Rudnicki
"""The unified ladder (0.12.0): every shutdown rung equals its gaming pay."""

from __future__ import annotations

from datetime import date, timedelta

from earned_time import (
    TUTOR_EARNERS,
    TUTOR_LADDER,
    UNIFIED_FROM,
    UNIFIED_LADDER,
    ladder_for,
    resolve,
    shutdown_ceiling_for,
)

EVE = UNIFIED_FROM - timedelta(days=1)


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _day(day: date, **done: int) -> tuple[int, str]:
    answers = {e.name: done.get(e.name, 0) for e in TUTOR_EARNERS}
    out = resolve(answers, day, TUTOR_EARNERS)
    return out.gaming_minutes, _hhmm(out.shutdown_minutes)


def test_switch_is_the_day_after_the_deploy() -> None:
    assert date(2026, 10, 18) == UNIFIED_FROM
    assert ladder_for(EVE) is TUTOR_LADDER  # deploy day keeps the old rungs
    assert ladder_for(UNIFIED_FROM) is UNIFIED_LADDER


def test_each_rung_pays_what_gaming_pays() -> None:
    for e in TUTOR_EARNERS:
        units = e.max_units or 1
        assert UNIFIED_LADDER[e.name].minutes(units) == e.gaming_for(units), e.name
    assert {n: r.minutes(60) for n, r in UNIFIED_LADDER.items()} == {
        "workout": 120,
        "leetcode": 60,
        "reading": 60,
        "tutor": 60,
    }


def test_ceiling_stays_and_floor_drops_to_18() -> None:
    assert shutdown_ceiling_for(UNIFIED_FROM) == 23 * 60
    assert _day(UNIFIED_FROM) == (180, "18:00")
    assert _day(UNIFIED_FROM, workout=1) == (300, "20:00")
    assert _day(UNIFIED_FROM, workout=2) == (300, "20:00")  # 2nd unit pays 0
    assert _day(UNIFIED_FROM, workout=1, leetcode=1) == (360, "21:00")
    assert _day(UNIFIED_FROM, workout=1, leetcode=1, reading=1) == (420, "22:00")
    full = _day(UNIFIED_FROM, workout=1, leetcode=1, reading=1, tutor=60)
    assert full == (480, "23:00")
    assert _day(UNIFIED_FROM, tutor=30) == (210, "18:30")  # per unit, 1:1


def test_old_days_keep_the_tutor_ladder() -> None:
    assert _day(EVE) == (180, "18:50")
    assert _day(EVE, workout=1) == (300, "20:40")
