# Copyright (c) 2026 Krzysztof Rudnicki
"""A gate whose penalty has not started spares the ladder floor (0.6.1).

Maturity may only raise time: the floor is never below 0.6.0's (the ceiling
minus every registered earner's rung), never above the ceiling, and passing
``first_credits`` never lowers anything.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import pytest

from earned_time import (
    AUTOMATION_TUTOR,
    EARNERS,
    LADDER_FROM,
    TUTOR_FROM,
    WORKOUT,
    Earner,
    base_for,
    earners_for,
    resolve,
    shutdown_ceiling_for,
)

DAY = timedelta(days=1)
LADDER_DAYS = (LADDER_FROM, LADDER_FROM + DAY, LADDER_FROM + 30 * DAY)
FIRSTS = ("missing", None, -5, 0, 3)
CONFIRMED = (None, -5, 3)
# What the real ledgers said on 2026-10-09: the tutor never paid out.
REAL = {
    "workout": date(2026, 10, 1),
    "leetcode": date(2026, 8, 12),
    "reading": date(2026, 10, 2),
    "automation": None,
}


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _head_floor(day: date, registry: tuple[Earner, ...]) -> int:
    """0.6.0's ladder floor: every registered rung, maturity ignored."""
    return shutdown_ceiling_for(day) - sum(
        e.shutdown_for(e.max_units or 1, day) for e in registry
    )


def _anchor(item: Earner) -> date:
    return item.penalty_from or date(2026, 9, 1)


def _registry(day: date, confirmed: int | None) -> tuple[Earner, ...]:
    return tuple(
        replace(
            e,
            confirmed_on=None if confirmed is None else _anchor(e) + confirmed * DAY,
        )
        for e in earners_for(day)
    )


def _firsts(
    registry: tuple[Earner, ...], first: str | int | None
) -> dict[str, date | None]:
    if first == "missing":
        return {}
    if first is None:
        return dict.fromkeys((e.name for e in registry), None)
    assert isinstance(first, int)
    return {e.name: _anchor(e) + first * DAY for e in registry}


@pytest.mark.parametrize("day", LADDER_DAYS)
@pytest.mark.parametrize("first", FIRSTS)
@pytest.mark.parametrize("confirmed", CONFIRMED)
@pytest.mark.parametrize("blocks", range(5))
@pytest.mark.parametrize("done", [0, 1])
def test_the_floor_only_ever_rises(
    day: date, first: str | int | None, confirmed: int | None, blocks: int, done: int
) -> None:
    registry = _registry(day, confirmed)
    answers = {e.name: done for e in registry} | {"automation": blocks}
    firsts = _firsts(registry, first)
    ceiling = shutdown_ceiling_for(day)
    head = _head_floor(day, registry)
    old = resolve(answers, day, registry)
    new = resolve(answers, day, registry, first_credits=firsts)
    earned = sum(t.shutdown_minutes for t in new.terms)
    assert head <= old.base.shutdown_minutes <= new.base.shutdown_minutes <= ceiling
    assert new.shutdown_minutes >= old.shutdown_minutes >= min(ceiling, head + earned)
    assert new.gaming_minutes >= old.gaming_minutes
    assert new.base.gaming_minutes >= old.base.gaming_minutes


@pytest.mark.parametrize("day", LADDER_DAYS)
@pytest.mark.parametrize("registry", [EARNERS, None])
def test_omitting_first_credits_keeps_0_6_0_on_the_real_registries(
    day: date, registry: tuple[Earner, ...] | None
) -> None:
    earners = earners_for(day) if registry is None else registry
    assert base_for(day, registry).shutdown_minutes == _head_floor(day, earners)


def test_a_never_paid_tutor_spares_the_first_tutor_day() -> None:
    assert TUTOR_FROM == LADDER_FROM == date(2026, 10, 10)
    base = base_for(TUTOR_FROM, first_credits=REAL)
    assert (base.gaming_minutes, _hhmm(base.shutdown_minutes)) == (240, "19:50")
    full = resolve(
        {"workout": 1, "leetcode": 1, "reading": 1, "automation": 4},
        TUTOR_FROM,
        first_credits=REAL,
    )
    assert (full.gaming_minutes, _hhmm(full.shutdown_minutes)) == (480, "23:00")
    # Unwired consumer (no first_credits): the tutor is cut from penalty_from.
    fallback = base_for(TUTOR_FROM)
    assert (fallback.gaming_minutes, _hhmm(fallback.shutdown_minutes)) == (
        180,
        "19:00",
    )


def test_the_floor_waits_for_the_day_after_the_first_block() -> None:
    paid = REAL | {"automation": TUTOR_FROM}
    for day, gaming, floor in (
        (TUTOR_FROM, 240, "19:50"),
        (TUTOR_FROM + DAY, 180, "19:00"),
    ):
        base = base_for(day, first_credits=paid)
        assert (base.gaming_minutes, _hhmm(base.shutdown_minutes)) == (gaming, floor)


def test_a_confirmed_tutor_with_no_credit_fails_closed_on_the_floor() -> None:
    confirmed = replace(AUTOMATION_TUTOR, confirmed_on=TUTOR_FROM - DAY)
    registry = (*earners_for(TUTOR_FROM)[:-1], confirmed)
    base = base_for(TUTOR_FROM, registry, first_credits=REAL)
    assert (base.gaming_minutes, _hhmm(base.shutdown_minutes)) == (180, "19:00")


def test_a_pure_bonus_is_always_on_the_ladder() -> None:
    assert WORKOUT.penalty_from is None
    never = base_for(TUTOR_FROM, (WORKOUT,), first_credits={"workout": None})
    assert never.shutdown_minutes == 23 * 60 - 110
    assert never.gaming_minutes == 300  # and never cut from gaming
