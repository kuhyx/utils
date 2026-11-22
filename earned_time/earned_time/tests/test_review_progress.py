# Copyright (c) 2026 Krzysztof Rudnicki
"""The review's partial pay: from REVIEW_PROGRESS_FROM no row means no pay."""

from __future__ import annotations

from datetime import date, timedelta
import logging
from typing import TYPE_CHECKING

import pytest

from earned_time import (
    REVIEW,
    REVIEW_FROM,
    REVIEW_PROGRESS_FROM,
    REVIEW_SHUTDOWN_MINUTES,
    Progress,
    progress_map,
    resolve,
)
from earned_time.tests._progress_rows import (
    home_ledger,
    progress,
    tampered,
    write,
)

if TYPE_CHECKING:
    from pathlib import Path

NOTHING: dict[str, int | bool | None] = {
    "workout": 0,
    "leetcode": False,
    "reading": False,
    "tutor": 0,
}
ON = date(2026, 11, 24)
DAYS = [ON, ON + timedelta(days=1), date(2027, 1, 1)]
Share = dict[str, Progress]


def _review(
    answer: int | None,
    day: date,
    *,
    sick: bool = False,
    progress: Share | None = None,
) -> int:
    answers = {**NOTHING, "review": answer}
    return resolve(answers, day, sick=sick, progress=progress).shutdown_minutes


def _paid(day: date, share: Share | None = None, *, sick: bool = False) -> int:
    """What the credited review adds to the day's shutdown over no review."""
    got = _review(1, day, sick=sick, progress=share)
    return got - _review(0, day, sick=sick, progress=share)


def test_the_switch_is_the_day_after_the_release() -> None:
    assert date(2026, 11, 24) == REVIEW_PROGRESS_FROM
    assert REVIEW_FROM + timedelta(days=1) == REVIEW_PROGRESS_FROM


def test_before_the_switch_the_review_pays_as_in_0_23_0() -> None:
    day = REVIEW_PROGRESS_FROM - timedelta(days=1)
    assert _paid(day) == REVIEW_SHUTDOWN_MINUTES
    # A row changes nothing yet: a yes pays full, a no pays nothing.
    half: Share = {"review": Progress(1, 2)}
    assert _paid(day, half) == REVIEW_SHUTDOWN_MINUTES
    assert _review(0, day, progress=half) == _review(0, day)


@pytest.mark.parametrize("day", DAYS)
def test_a_credited_review_with_no_row_pays_nothing(day: date) -> None:
    assert _paid(day) == 0
    assert _paid(day, {}) == 0
    assert _paid(day, {"leetcode": Progress(1, 2)}) == 0
    term = resolve({**NOTHING, "review": True}, day).term("review")
    assert (term.shutdown_minutes, term.gaming_minutes, term.progress) == (0, 0, None)
    assert term.answer == 1


@pytest.mark.parametrize("day", DAYS)
def test_a_row_pays_equal_slices_of_the_bonus(day: date) -> None:
    assert _paid(day, {"review": Progress(1, 2)}) == 10
    assert _paid(day, {"review": Progress(2, 2)}) == 20
    assert _paid(day, {"review": Progress(0, 2)}) == 0
    assert _paid(day, {"review": Progress(1, 3)}) == 20 // 3
    assert _paid(day, {"review": Progress(2, 3)}) == 40 // 3


def test_a_row_never_pays_more_than_the_full_bonus() -> None:
    assert _paid(ON, {"review": Progress(9, 2)}) == 20
    assert _paid(ON, {"review": Progress(5, 5)}) == 20


def test_the_term_shows_the_row_it_was_paid_from() -> None:
    row = Progress(1, 2)
    term = resolve({**NOTHING, "review": 1}, ON, progress={"review": row}).term(
        "review"
    )
    assert term.progress == row
    assert term.gaming_minutes == 0


@pytest.mark.parametrize("answer", [0, None])
def test_a_row_without_a_credited_review_pays_nothing(
    answer: int | None,
) -> None:
    full: Share = {"review": Progress(2, 2)}
    assert _review(answer, ON, progress=full) == _review(0, ON)
    term = resolve({**NOTHING, "review": answer}, ON, progress=full).term("review")
    assert term.shutdown_minutes == 0
    assert term.progress is None


def test_a_sick_day_follows_the_same_rule() -> None:
    assert _paid(ON, sick=True) == 0
    assert _paid(ON, {"review": Progress(1, 2)}, sick=True) == 10
    assert _paid(ON, {"review": Progress(2, 2)}, sick=True) == 20


def test_other_earners_keep_the_yes_no_rule_without_a_row() -> None:
    plain = resolve({**NOTHING, "leetcode": True}, ON)
    assert plain.term("leetcode").shutdown_minutes == 60
    shown = resolve(NOTHING, ON, progress={"leetcode": Progress(1, 3)})
    assert shown.term("leetcode").shutdown_minutes == 20
    assert resolve(NOTHING, ON).term("leetcode").shutdown_minutes == 0


def test_a_missing_review_answer_still_earns_nothing() -> None:
    answers = dict(NOTHING)
    shown = resolve(answers, ON, progress={"review": Progress(2, 2)})
    assert shown.term("review").shutdown_minutes == 0


def test_a_credited_review_without_a_row_is_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="earned_time._share"):
        resolve({**NOTHING, "review": True}, ON)
    assert "no progress row" in caplog.text
    assert REVIEW.label in caplog.text


def test_no_warning_with_a_row_or_before_the_switch(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="earned_time._share"):
        resolve({**NOTHING, "review": True}, ON, progress={"review": Progress(1, 2)})
        resolve({**NOTHING, "review": True}, REVIEW_FROM)
    assert "no progress row" not in caplog.text


def test_a_row_that_fails_verification_counts_as_no_row(
    tmp_path: Path, key_file: Path
) -> None:
    good = progress(source="review", done="2", target="2", day=ON)
    forged = tampered(good, done="2")
    forged["hmac"] = "0" * 64
    for rows, expected in (([good], 20), ([forged], 0), ([], 0)):
        write(home_ledger(tmp_path, REVIEW), list(rows))
        share = progress_map(ON, tmp_path, key_file)
        assert _paid(ON, share) == expected


def test_the_last_good_row_prices_the_day(tmp_path: Path, key_file: Path) -> None:
    rows = [
        progress(source="review", done="1", target="2", day=ON),
        progress(source="review", done="2", target="2", day=ON),
    ]
    write(home_ledger(tmp_path, REVIEW), list(rows))
    assert _paid(ON, progress_map(ON, tmp_path, key_file)) == 20
    write(home_ledger(tmp_path, REVIEW), list(rows[:1]))
    assert _paid(ON, progress_map(ON, tmp_path, key_file)) == 10
