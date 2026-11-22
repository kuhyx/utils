# Copyright (c) 2026 Krzysztof Rudnicki
"""Partial pay: a share of the full pay for a no, never more than a yes."""

from __future__ import annotations

from datetime import date, datetime, time
from itertools import product
from typing import TYPE_CHECKING

import pytest

from earned_time import (
    LEETCODE,
    REVIEW,
    Earner,
    FocusEarner,
    Progress,
    credit_units,
    done_today,
    maturity,
    progress_map,
    resolve,
    shutdown_minutes_for,
)
from earned_time._share import share_minutes
from earned_time.tests._maturity_rows import solve
from earned_time.tests._progress_rows import DAY, home_ledger, progress, write

if TYPE_CHECKING:
    from pathlib import Path

# A day on the unified ladder: LeetCode pays 60 and shuts down 60 later.
LADDER = date(2026, 11, 22)
NOTHING: dict[str, int | bool | None] = {
    "workout": 0,
    "leetcode": False,
    "reading": False,
    "tutor": 0,
}


def test_sixty_times_one_over_three_is_twenty_through_resolve() -> None:
    day = resolve(NOTHING, LADDER, progress={"leetcode": Progress(1, 3)})
    term = day.term("leetcode")
    assert (term.gaming_minutes, term.shutdown_minutes) == (20, 20)
    assert day.shutdown_minutes == resolve(NOTHING, LADDER).shutdown_minutes + 20


def test_a_true_answer_pays_full_whatever_the_row_says() -> None:
    answers = {**NOTHING, "leetcode": True}
    plain = resolve(answers, LADDER)
    shown = resolve(answers, LADDER, progress={"leetcode": Progress(1, 3)})
    assert shown == plain
    assert shown.term("leetcode").progress is None


def test_an_answer_of_none_earns_nothing_even_with_a_full_row() -> None:
    answers = {**NOTHING, "leetcode": None}
    shown = resolve(answers, LADDER, progress={"leetcode": Progress(3, 3)})
    assert shown == resolve(answers, LADDER)
    assert shown.term("leetcode").shutdown_minutes == 0


def test_a_missing_answer_earns_nothing_even_with_a_full_row() -> None:
    answers = {k: v for k, v in NOTHING.items() if k != "leetcode"}
    shown = resolve(answers, LADDER, progress={"leetcode": Progress(3, 3)})
    assert shown.term("leetcode").shutdown_minutes == 0


def test_a_complete_row_with_a_no_answer_pays_in_full() -> None:
    shown = resolve(NOTHING, LADDER, progress={"leetcode": Progress(3, 3)})
    assert shown.term("leetcode").shutdown_minutes == 60
    assert shown.term("leetcode").gaming_minutes == 60


def test_the_share_floors() -> None:
    shown = resolve(NOTHING, LADDER, progress={"leetcode": Progress(1, 7)})
    assert shown.term("leetcode").shutdown_minutes == 60 // 7


def test_term_progress_says_why() -> None:
    shown = resolve(NOTHING, LADDER, progress={"leetcode": Progress(2, 3)})
    assert shown.term("leetcode").progress == Progress(2, 3)
    assert shown.term("leetcode").answer == 0
    assert shown.term("reading").progress is None


def test_a_counted_workout_pays_a_share_of_its_rung() -> None:
    shown = resolve(NOTHING, LADDER, progress={"workout": Progress(1, 2)})
    assert shown.term("workout").shutdown_minutes == 120 // 2
    assert shown.term("workout").gaming_minutes == 120 // 2


def test_a_pre_ladder_day_shares_the_old_pay() -> None:
    day = date(2026, 10, 4)
    shown = resolve(NOTHING, day, progress={"reading": Progress(1, 4)})
    assert shown.term("reading").shutdown_minutes == 60 // 4


def test_the_share_uses_the_ladder_rung_not_the_old_pay() -> None:
    day = date(2026, 10, 16)
    assert shutdown_minutes_for(LEETCODE, day) == 50
    shown = resolve(NOTHING, day, progress={"leetcode": Progress(1, 2)})
    assert shown.term("leetcode").shutdown_minutes == 25
    assert shown.term("leetcode").gaming_minutes == 30


def test_the_review_pays_a_share_of_its_top_up() -> None:
    answers = {**NOTHING, "review": False}
    shown = resolve(answers, DAY, progress={"review": Progress(1, 2)})
    assert shown.term("review").shutdown_minutes == 10
    paid = resolve(
        {**NOTHING, "review": True}, DAY, progress={"review": Progress(1, 2)}
    )
    assert paid.term("review").shutdown_minutes == 20


def test_a_progress_for_an_earner_not_in_the_registry_is_ignored() -> None:
    answers = {k: v for k, v in NOTHING.items() if k != "tutor"}
    got = resolve(answers, date(2026, 10, 4), progress={"tutor": Progress(1, 2)})
    assert got == resolve(answers, date(2026, 10, 4))


def test_a_sick_day_pays_the_partial_on_top_of_eight_pm() -> None:
    day = resolve(NOTHING, LADDER, sick=True, progress={"leetcode": Progress(1, 3)})
    assert day.shutdown_minutes == 20 * 60 + 20


def test_a_sick_day_partials_stack_and_stop_at_the_ceiling() -> None:
    both = {"leetcode": Progress(3, 3), "reading": Progress(3, 3)}
    day = resolve({**NOTHING, "workout": 1}, LADDER, sick=True, progress=both)
    assert day.shutdown_minutes == 23 * 60


def test_a_sick_day_with_a_none_answer_gets_no_partial() -> None:
    answers = {**NOTHING, "leetcode": None}
    day = resolve(answers, LADDER, sick=True, progress={"leetcode": Progress(3, 3)})
    assert day.shutdown_minutes == 20 * 60


@pytest.mark.parametrize("answers", [NOTHING, {**NOTHING, "leetcode": True}])
def test_a_progress_row_never_pays_more_than_a_yes(
    answers: dict[str, int | bool | None],
) -> None:
    yes = resolve({**NOTHING, "leetcode": True}, LADDER)
    for done, target in product(range(6), range(1, 6)):
        got = resolve(answers, LADDER, progress={"leetcode": Progress(done, target)})
        assert got.shutdown_minutes <= yes.shutdown_minutes
        assert got.gaming_minutes <= yes.gaming_minutes


def test_deleting_rows_never_raises_the_pay_at_one_target(
    tmp_path: Path, key_file: Path
) -> None:
    rows = [progress(done=str(n), target="4") for n in (0, 1, 2, 3)]
    full = _pay(tmp_path, key_file, rows)
    for mask in product((False, True), repeat=len(rows)):
        kept: list[object] = [r for r, keep in zip(rows, mask, strict=True) if keep]
        assert _pay(tmp_path, key_file, kept) <= full


def _pay(tmp_path: Path, key_file: Path, rows: list[object]) -> int:
    write(home_ledger(tmp_path, LEETCODE), rows)
    found = progress_map(DAY, tmp_path, key_file)
    return resolve(NOTHING, DAY, progress=found).shutdown_minutes


def test_gate_off_keeps_progress_out_of_the_pay(tmp_path: Path, key_file: Path) -> None:
    write(home_ledger(tmp_path, LEETCODE), [progress(done="2", target="3")])
    on = progress_map(DAY, tmp_path, key_file)
    off = progress_map(DAY, tmp_path, key_file, gate_off={"leetcode"})
    assert resolve(NOTHING, DAY, progress=on).term("leetcode").shutdown_minutes == 40
    assert resolve(NOTHING, DAY, progress=off).term("leetcode").shutdown_minutes == 0


def test_a_progress_row_is_not_a_credit_for_maturity(
    tmp_path: Path, key_file: Path
) -> None:
    today = date(2026, 10, 9)
    solves: list[object] = [solve(date(2026, 10, 1)), solve(date(2026, 10, 5))]
    extra = [progress(day=today, done="3", target="3"), progress(done="1")]
    bare = write(tmp_path / "bare.json", solves)
    mixed = write(tmp_path / "mixed.json", [*solves, *extra])
    assert maturity(LEETCODE, mixed, key_file, today) == maturity(
        LEETCODE, bare, key_file, today
    )
    alone = write(tmp_path / "alone.json", extra)
    seen = maturity(LEETCODE, alone, key_file, today)
    assert (seen.credit_days, seen.credit_rows, seen.first_credit) == (0, 0, None)


def test_a_progress_row_is_not_a_done_answer(tmp_path: Path, key_file: Path) -> None:
    ledger = write(home_ledger(tmp_path, LEETCODE), [progress(done="3", target="3")])
    assert done_today(LEETCODE, ledger, key_file, now=_noon(DAY)) is False
    assert credit_units(LEETCODE, ledger, key_file, DAY) == 0


def _noon(day: date) -> datetime:
    return datetime.combine(day, time(12)).astimezone()


@pytest.mark.parametrize("pay", [0, 1, 7, 60, 100, 120, 180, 240])
@pytest.mark.parametrize("target", [1, 2, 3, 7, 60, 120])
def test_the_focus_share_floors_exactly_as_before(pay: int, target: int) -> None:
    earner = FocusEarner(
        name="focus",
        label="Focus",
        gaming_minutes=pay,
        shutdown_minutes=pay,
        kind="counted",
        max_units=target,
    )
    for units in range(-2, target + 3):
        clamped = min(max(units, 0), target)
        assert earner.gaming_for(units) == clamped * pay // target
        assert earner.shutdown_for(units, DAY) == clamped * pay // target
        assert share_minutes(pay, units, target) == clamped * pay // target


def test_the_share_of_a_zero_target_is_nothing() -> None:
    assert share_minutes(60, 5, 0) == 0
    assert share_minutes(60, -1, 3) == 0


def test_progress_source_defaults_to_none() -> None:
    assert Earner("x", "x", 1, 1).progress_source is None
    assert REVIEW.progress_source == "review"
