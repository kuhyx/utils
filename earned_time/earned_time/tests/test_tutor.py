# Copyright (c) 2026 Krzysztof Rudnicki
"""The tutor cutover: Anki retired, Automation paid per active minute (0.8.0)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from earned_time import (
    AUTOMATION,
    AUTOMATION_TUTOR,
    EARNERS,
    LADDER,
    LADDER_FROM,
    TUTOR_EARNERS,
    TUTOR_FROM,
    TUTOR_LADDER,
    WORKOUT,
    Rung,
    all_earners,
    base_for,
    earners_for,
    extra_shutdown_minutes_for,
    ladder_for,
    resolve,
)

EVE = TUTOR_FROM - timedelta(days=1)
OTHERS = {"workout": 1, "leetcode": 1, "reading": 1}


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _day(minutes: int, **others: int) -> tuple[int, str]:
    day = resolve({**others, "automation": minutes}, TUTOR_FROM)
    return day.gaming_minutes, _hhmm(day.shutdown_minutes)


def test_tutor_from_is_the_day_after_the_deploy() -> None:
    assert date(2026, 10, 10) == TUTOR_FROM
    assert date(2026, 10, 9) < TUTOR_FROM  # never the day it was prepared
    assert LADDER_FROM <= TUTOR_FROM
    # Confirmed the eve, so the penalty bites on TUTOR_FROM itself.
    assert AUTOMATION_TUTOR.confirmed_on == EVE


def test_registry_switches_on_tutor_from() -> None:
    assert earners_for(EVE) is not TUTOR_EARNERS  # the waiver (ANKI_WAIVED_FROM)
    assert earners_for(None) is earners_for(datetime.now().astimezone().date())
    assert earners_for(TUTOR_FROM) is TUTOR_EARNERS
    assert "anki" not in {e.name for e in TUTOR_EARNERS}
    assert ladder_for(EVE) is None  # the eve is pre-ladder
    # TUTOR_FROM == LADDER_FROM: the first ladder day already has the tutor's.
    assert ladder_for(LADDER_FROM) is TUTOR_LADDER
    assert ladder_for(date(2026, 10, 1)) is None


def test_all_earners_lists_each_once() -> None:
    names = [e.name for e in all_earners()]
    assert names.count("workout") == 1
    assert AUTOMATION in all_earners()
    assert AUTOMATION_TUTOR in all_earners()


def test_each_tutor_minute_earns_the_minute_it_costs() -> None:
    # The fairness rule: no unit costs more than the shutdown it earns. The
    # rungs, each at its earner's cap, still span 250 (23:00 down to 18:50).
    assert sum(r.minutes(4) for r in LADDER.values()) == 240
    full = {
        e.name: TUTOR_LADDER[e.name].minutes(e.max_units or 1) for e in TUTOR_EARNERS
    }
    assert full == {"workout": 110, "leetcode": 50, "reading": 30, "automation": 60}
    assert sum(full.values()) == 250
    for n in range(61):
        assert AUTOMATION_TUTOR.shutdown_for(n, TUTOR_FROM) == n
        assert AUTOMATION_TUTOR.gaming_for(n) == n


def test_nothing_done_is_three_hours_and_18_50() -> None:
    # Confirmed, so the tutor is cut from penalty_from with or without
    # first_credits (test_maturity_floor.py).
    assert _day(0) == (180, "18:50")
    assert base_for(TUTOR_FROM).gaming_minutes == 180


def test_everything_but_the_tutor() -> None:
    assert _day(0, **OTHERS) == (420, "22:00")


@pytest.mark.parametrize(
    ("minutes", "gaming", "shutdown"),
    [
        (1, 421, "22:01"),
        (15, 435, "22:15"),
        (30, 450, "22:30"),
        (59, 479, "22:59"),
        (60, 480, "23:00"),
    ],
)
def test_each_minute_pays_1_gaming_and_1_shutdown(
    minutes: int, gaming: int, shutdown: str
) -> None:
    assert _day(minutes, **OTHERS) == (gaming, shutdown)


def test_partial_credit_without_the_others() -> None:
    assert _day(1) == (181, "18:51")
    assert _day(15) == (195, "19:05")  # one legacy block, as 0.7.0 paid it
    assert _day(60) == (240, "19:50")


def test_minutes_past_60_are_clamped() -> None:
    assert _day(61, **OTHERS) == _day(60, **OTHERS) == (480, "23:00")
    term = resolve({"automation": 75}, TUTOR_FROM).term("automation")
    assert (term.answer, term.gaming_minutes, term.shutdown_minutes) == (75, 60, 60)


def test_anki_is_neither_penalised_nor_paid_from_tutor_from() -> None:
    with_anki = resolve({**OTHERS, "anki": 1, "automation": 60}, TUTOR_FROM)
    assert (with_anki.gaming_minutes, with_anki.shutdown_minutes) == (480, 23 * 60)
    assert "anki" not in {t.earner.name for t in with_anki.terms}


def test_the_eve_resolves_as_before() -> None:
    # The eve is pre-ladder: 20:00 minus the cuts in force, plus the terms.
    eve = resolve({**OTHERS, "anki": 0, "automation": 0}, EVE, EARNERS)
    assert eve.base.gaming_minutes == 180
    assert (eve.gaming_minutes, _hhmm(eve.shutdown_minutes)) == (420, "22:00")
    done = resolve({**OTHERS, "anki": 1, "automation": 1}, EVE, EARNERS)
    assert (done.gaming_minutes, _hhmm(done.shutdown_minutes)) == (480, "23:00")
    assert done.term("automation").earner is AUTOMATION


def test_unknown_names_still_raise() -> None:
    with pytest.raises(KeyError, match="piano"):
        resolve({"piano": 1}, TUTOR_FROM)


def test_rung_steps_and_extras() -> None:
    rung = Rung(13, steps=(13, 12, 12))
    assert [rung.minutes(n) for n in range(6)] == [0, 13, 26, 38, 50, 50]
    assert rung.second == 13
    assert Rung(10, extra=5).minutes(3) == 20
    assert Rung(10, extra=5).second == 5
    assert extra_shutdown_minutes_for(AUTOMATION_TUTOR, TUTOR_FROM) == 1


def test_gaming_for_and_max() -> None:
    gaming = [AUTOMATION_TUTOR.gaming_for(n) for n in (-1, 0, 1, 15, 60, 90)]
    assert gaming == [0, 0, 1, 15, 60, 60]
    assert AUTOMATION_TUTOR.max_gaming_minutes == 60
    assert WORKOUT.max_gaming_minutes == WORKOUT.gaming_minutes
    assert WORKOUT.gaming_for(3) == WORKOUT.gaming_minutes


def test_tutor_shutdown_before_the_ladder_uses_its_own_fields() -> None:
    old = date(2026, 10, 1)
    assert AUTOMATION_TUTOR.shutdown_for(2, old) == 2
    assert AUTOMATION_TUTOR.shutdown_for(0, old) == 0
