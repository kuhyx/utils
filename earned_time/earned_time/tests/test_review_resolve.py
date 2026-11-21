# Copyright (c) 2026 Krzysztof Rudnicki
"""The review top-up in the day (0.23.0): added last, capped, never a rung."""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

from earned_time import (
    REVIEW,
    REVIEW_FROM,
    REVIEW_SHUTDOWN_MINUTES,
    all_earners,
    base_for,
    earners_for,
    maturity,
    resolve,
    shutdown_ceiling_for,
    shutdown_minutes_for,
)
from earned_time.tests._review_rows import DAY, accepted, home_with, review

if TYPE_CHECKING:
    from pathlib import Path

NOTHING: dict[str, int | bool | None] = {
    "workout": 0,
    "leetcode": False,
    "reading": False,
    "tutor": 0,
}
EVERYTHING: dict[str, int | bool | None] = {
    "workout": 1,
    "leetcode": True,
    "reading": True,
    "tutor": 60,
}


def _day(answers: dict[str, int | bool | None], **kwargs: bool) -> int:
    return resolve(answers, DAY, **kwargs).shutdown_minutes


def test_the_constants() -> None:
    assert REVIEW_SHUTDOWN_MINUTES == 20
    assert date(2026, 11, 23) == REVIEW_FROM
    assert REVIEW.gaming_minutes == 0
    assert REVIEW.topup
    assert REVIEW.penalty_from is None
    assert REVIEW.confirmed_on is None


def test_the_review_pays_twenty_flat() -> None:
    with_review = _day({**NOTHING, "review": True})
    assert with_review - _day({**NOTHING, "review": False}) == REVIEW_SHUTDOWN_MINUTES
    assert shutdown_minutes_for(REVIEW, DAY) == REVIEW_SHUTDOWN_MINUTES


def test_two_units_still_pay_twenty() -> None:
    assert _day({**NOTHING, "review": 2}) == _day({**NOTHING, "review": 1})
    assert resolve({**NOTHING, "review": 2}, DAY).term("review").shutdown_minutes == 20


def test_it_is_capped_at_the_ceiling() -> None:
    near = {**EVERYTHING, "tutor": 50}
    assert _day(near) == shutdown_ceiling_for(DAY) - 10
    assert _day({**near, "review": True}) == shutdown_ceiling_for(DAY)


def test_it_is_worth_nothing_on_a_full_day() -> None:
    full = _day({**EVERYTHING, "review": False})
    assert full == shutdown_ceiling_for(DAY)
    assert _day({**EVERYTHING, "review": True}) == full


def test_the_floor_does_not_move() -> None:
    without = tuple(e for e in earners_for(DAY) if e is not REVIEW)
    assert base_for(DAY) == base_for(DAY, without)
    assert _day({**NOTHING, "review": False}) == base_for(DAY).shutdown_minutes
    assert _day({**NOTHING, "review": None}) == base_for(DAY).shutdown_minutes


def test_could_not_check_earns_nothing_but_says_so() -> None:
    term = resolve({**NOTHING, "review": None}, DAY).term("review")
    assert term.answer is None
    assert term.shutdown_minutes == 0


def test_not_registered_before_the_start_date() -> None:
    before = REVIEW_FROM - timedelta(days=1)
    assert REVIEW not in earners_for(before)
    assert REVIEW in earners_for(REVIEW_FROM)
    assert resolve({**NOTHING, "review": True}, before).shutdown_minutes == (
        resolve(NOTHING, before).shutdown_minutes
    )


def test_every_registry_view_watches_its_ledger() -> None:
    assert REVIEW in all_earners()


def test_a_sick_day_adds_it_on_top() -> None:
    sick = _day({**NOTHING, "review": False}, sick=True)
    assert _day({**NOTHING, "review": True}, sick=True) == sick + 20


def test_a_full_sick_day_stays_at_the_ceiling() -> None:
    assert _day({**EVERYTHING, "review": True}, sick=True) == shutdown_ceiling_for(DAY)


def test_a_sick_day_before_unlimited_gaming_adds_it_too() -> None:
    old = date(2026, 11, 1)
    registry = (*earners_for(old), REVIEW)
    base = resolve({**NOTHING, "review": False}, old, registry, sick=True)
    paid = resolve({**NOTHING, "review": True}, old, registry, sick=True)
    assert paid.shutdown_minutes == base.shutdown_minutes + 20


def test_maturity_never_penalises_it(tmp_path: Path, key_file: Path) -> None:
    ledger = home_with(tmp_path, [review()], [accepted()])
    verdict = maturity(REVIEW, ledger, key_file, DAY)
    assert verdict.penalty_start is None
    assert any("top-up" in reason for reason in verdict.reasons)
