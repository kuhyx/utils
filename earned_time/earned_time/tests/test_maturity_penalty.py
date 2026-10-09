# Copyright (c) 2026 Krzysztof Rudnicki
"""Maturity only ever delays a penalty: ``first_credits`` vs 0.5.0's resolve."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import pytest

from earned_time import (
    ANKI_WAIVED_FROM,
    LADDER_FROM,
    READING,
    Earner,
    base_for,
    confirmed_start,
    earners_for,
    penalty_start,
    resolve,
)

DAY = timedelta(days=1)
# Pre-waiver (reading cut only), pre-waiver with Anki/Automation cut too,
# the first waiver day, and the first ladder day.
DAYS = (date(2026, 10, 3), date(2026, 10, 7), ANKI_WAIVED_FROM, LADDER_FROM)
# A first credit relative to each earner's penalty_from; "missing" leaves the
# earner out of the map, None is "never paid out / could not check".
FIRSTS = ("missing", None, -5, 0, 3)
CONFIRMED = (None, -5, 3)


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


@pytest.mark.parametrize("day", DAYS)
@pytest.mark.parametrize("first", FIRSTS)
@pytest.mark.parametrize("confirmed", CONFIRMED)
@pytest.mark.parametrize("done", [0, 1])
def test_raise_only_on_every_combination(
    day: date, first: str | int | None, confirmed: int | None, done: int
) -> None:
    registry = _registry(day, confirmed)
    answers = {e.name: done for e in registry}
    old = resolve(answers, day, registry)  # 0.5.0: no first_credits
    new = resolve(answers, day, registry, first_credits=_firsts(registry, first))
    assert new.gaming_minutes >= old.gaming_minutes
    assert new.shutdown_minutes >= old.shutdown_minutes
    assert new.base.gaming_minutes >= old.base.gaming_minutes
    assert new.base.shutdown_minutes >= old.base.shutdown_minutes
    if first == -5 and confirmed in {None, -5}:
        # Paid out and confirmed well before the cut: exactly 0.5.0.
        assert new == old


def test_omitting_first_credits_is_0_5_0() -> None:
    for day in DAYS:
        registry = earners_for(day)
        old = [e for e in registry if e.penalised_on(day)]
        expected = 300 - sum(e.max_gaming_minutes for e in old)
        assert base_for(day).gaming_minutes == expected


def test_an_unconfirmed_gate_that_never_paid_out_costs_nothing() -> None:
    day = date(2026, 10, 3)
    unconfirmed = replace(READING, confirmed_on=None)
    registry = (unconfirmed,)
    cut = base_for(day, registry)
    lifted = base_for(day, registry, first_credits={"reading": None})
    assert lifted.gaming_minutes - cut.gaming_minutes == READING.max_gaming_minutes
    assert lifted.shutdown_minutes - cut.shutdown_minutes == READING.shutdown_minutes


def test_a_confirmed_gate_with_no_credit_on_record_fails_closed() -> None:
    # Could not check, or the ledger was deleted: Maturity.first_credit None.
    assert READING.confirmed_on == date(2026, 10, 2)
    assert penalty_start(READING, None) == date(2026, 10, 3)
    for day, penalised in ((date(2026, 10, 2), False), (date(2026, 10, 3), True)):
        base = base_for(day, (READING,), first_credits={"reading": None})
        assert base.gaming_minutes == 300 - 60 * penalised


def test_the_penalty_waits_for_the_day_after_the_first_credit() -> None:
    first = {"reading": date(2026, 10, 2)}
    assert READING.penalty_from == date(2026, 10, 1)
    for day, penalised in (
        (date(2026, 10, 1), False),
        (date(2026, 10, 2), False),
        (date(2026, 10, 3), True),
    ):
        base = base_for(day, (READING,), first_credits=first)
        assert base.gaming_minutes == 300 - 60 * penalised


def test_a_missing_earner_still_waits_for_its_confirmation() -> None:
    late = replace(READING, confirmed_on=date(2026, 10, 4))
    assert confirmed_start(late) == date(2026, 10, 5)
    for day, penalised in ((date(2026, 10, 4), False), (date(2026, 10, 5), True)):
        base = base_for(day, (late,), first_credits={})
        assert base.gaming_minutes == 300 - 60 * penalised


def test_penalty_start_never_precedes_penalty_from() -> None:
    bonus = replace(READING, penalty_from=None)
    assert confirmed_start(bonus) is None
    assert penalty_start(bonus, date(2026, 1, 1)) is None
    unconfirmed = replace(READING, confirmed_on=None)
    assert confirmed_start(unconfirmed) == READING.penalty_from
    assert penalty_start(unconfirmed, date(2026, 1, 1)) == READING.penalty_from
    assert penalty_start(unconfirmed, None) is None
    early = replace(READING, confirmed_on=date(2026, 9, 1))
    assert confirmed_start(early) == READING.penalty_from
    assert penalty_start(early, None) == READING.penalty_from


def test_a_pure_bonus_is_never_penalised_with_a_map() -> None:
    bonus = replace(READING, penalty_from=None)
    base = base_for(date(2026, 10, 3), (bonus,), first_credits={"reading": None})
    assert base.gaming_minutes == 300
