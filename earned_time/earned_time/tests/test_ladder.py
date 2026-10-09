# Copyright (c) 2026 Krzysztof Rudnicki
"""The shutdown ladder: dated switch, wake anchor, and gaming left untouched."""

from __future__ import annotations

from datetime import date

import pytest

from earned_time import (
    ANKI,
    AUTOMATION,
    EARNERS,
    LADDER,
    LADDER_FROM,
    LEETCODE,
    READING,
    SHUTDOWN_CEILING_MINUTES,
    WAKE_MINUTES,
    WORKOUT,
    Earner,
    Rung,
    base_for,
    extra_shutdown_minutes_for,
    on_ladder,
    resolve,
    shutdown_ceiling_for,
    shutdown_minutes_for,
)
import earned_time._ladder as ladder

EVE = date(2026, 10, 9)
FIRST = date(2026, 10, 10)
NAMES = [e.name for e in EARNERS]


@pytest.fixture(autouse=True)
def _pre_tutor_ladder(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the tutor cutover out of the way of ``LADDER``'s own arithmetic.

    Since 0.6.1 ``TUTOR_FROM == LADDER_FROM``, so no real day resolves on
    ``LADDER``; these tests pin the ladder mechanism on it regardless (the
    tutor's rungs: ``test_tutor.py``).
    """
    monkeypatch.setattr(ladder, "TUTOR_FROM", date(2099, 1, 1))


def _shutdown(day: date, **done: int) -> str:
    answers = {name: done.get(name, 0) for name in NAMES}
    minutes = resolve(answers, day, EARNERS).shutdown_minutes
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _gaming(day: date, **done: int) -> int:
    return resolve(
        {name: done.get(name, 0) for name in NAMES}, day, EARNERS
    ).gaming_minutes


def test_switch_date_and_wake_anchor() -> None:
    assert LADDER_FROM == FIRST
    assert WAKE_MINUTES == 7 * 60
    assert not on_ladder(EVE)
    assert on_ladder(FIRST)


def test_ceiling_is_eight_hours_before_wake() -> None:
    assert shutdown_ceiling_for(FIRST) == 23 * 60
    assert shutdown_ceiling_for(EVE) == SHUTDOWN_CEILING_MINUTES


def test_ceiling_follows_the_alarm_but_old_days_stay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ladder, "WAKE_MINUTES", 6 * 60)
    assert shutdown_ceiling_for(FIRST) == 22 * 60
    assert base_for(FIRST, EARNERS).shutdown_minutes == 18 * 60
    assert shutdown_ceiling_for(EVE) == 23 * 60
    assert base_for(EVE, EARNERS).shutdown_minutes == 18 * 60


@pytest.mark.parametrize(
    ("item", "eve", "first"),
    [
        (WORKOUT, 120, 110),
        (LEETCODE, 60, 50),
        (READING, 60, 30),
        (ANKI, 30, 25),
        (AUTOMATION, 30, 25),
    ],
)
def test_shutdown_minutes_for(item: Earner, eve: int, first: int) -> None:
    assert shutdown_minutes_for(item, EVE) == eve
    assert shutdown_minutes_for(item, FIRST) == first


def test_every_earner_has_a_rung() -> None:
    assert set(LADDER) == {e.name for e in EARNERS}
    assert LADDER["workout"] == Rung(110, 0)


def test_first_units_fill_the_gap_exactly() -> None:
    total = sum(shutdown_minutes_for(e, FIRST) for e in EARNERS)
    assert total == 240
    assert (
        base_for(FIRST, EARNERS).shutdown_minutes == shutdown_ceiling_for(FIRST) - total
    )


def test_extra_workouts_earn_nothing_on_the_ladder() -> None:
    assert extra_shutdown_minutes_for(WORKOUT, EVE) == 60
    assert extra_shutdown_minutes_for(WORKOUT, FIRST) == 0
    assert extra_shutdown_minutes_for(LEETCODE, FIRST) == 0
    assert [WORKOUT.shutdown_for(n, FIRST) for n in range(4)] == [0, 110, 110, 110]


def test_earner_without_ladder_values_keeps_its_own() -> None:
    plain = Earner(
        name="plain",
        label="plain",
        gaming_minutes=0,
        shutdown_minutes=15,
        kind="counted",
        extra_shutdown_minutes=5,
    )
    assert shutdown_minutes_for(plain, FIRST) == 15
    assert extra_shutdown_minutes_for(plain, FIRST) == 5


def test_shutdown_for_defaults_to_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ladder, "LADDER_FROM", date(2000, 1, 1))
    assert WORKOUT.shutdown_for(2) == 110


def test_the_ladder() -> None:
    assert _shutdown(FIRST) == "19:00"
    steps = ["workout", "leetcode", "reading", "anki", "automation"]
    expected = ["20:50", "21:40", "22:10", "22:35", "23:00"]
    for count, want in enumerate(expected, start=1):
        assert _shutdown(FIRST, **dict.fromkeys(steps[:count], 1)) == want
    assert _shutdown(FIRST, workout=2) == "20:50"
    assert _shutdown(FIRST, **dict.fromkeys(steps, 1) | {"workout": 3}) == "23:00"


def test_the_eve_resolves_the_old_way() -> None:
    assert _shutdown(EVE) == "18:00"
    assert _shutdown(EVE, workout=2) == "21:00"
    assert _shutdown(EVE, workout=1, leetcode=1, reading=1, anki=1) == "22:30"


@pytest.mark.parametrize("done", [{}, {"workout": 2}, dict.fromkeys(NAMES, 1)])
def test_gaming_is_the_same_on_both_sides_of_the_switch(done: dict[str, int]) -> None:
    assert _gaming(EVE, **done) == _gaming(FIRST, **done)
    assert (
        base_for(EVE, EARNERS).gaming_minutes
        == base_for(FIRST, EARNERS).gaming_minutes
        == 180
    )
