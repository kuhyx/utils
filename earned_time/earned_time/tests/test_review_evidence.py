# Copyright (c) 2026 Krzysztof Rudnicki
"""Which coach review rows pay (0.23.0): signed, sourced, backed, first per slug."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import TYPE_CHECKING

import pytest

from earned_time import (
    ACCEPTED_LOOKBACK_DAYS,
    GUARD_LEDGER,
    LEETCODE,
    REVIEW,
    credit_units,
    done_today,
)
from earned_time.tests._review_rows import (
    DAY,
    accepted,
    evening,
    home_with,
    review,
    sign,
)

if TYPE_CHECKING:
    from pathlib import Path


def _done(home: Path, key_file: Path, reviews: list, guard: list | None) -> object:
    ledger = home_with(home, reviews, guard)
    return done_today(REVIEW, ledger, key_file, now=evening())


def test_the_guard_ledger_is_the_leetcode_earners() -> None:
    assert LEETCODE.ledger == GUARD_LEDGER


def test_a_backed_review_pays(tmp_path: Path, key_file: Path) -> None:
    assert _done(tmp_path, key_file, [review()], [accepted()]) is True


def test_two_reviews_in_a_day_are_one_unit(tmp_path: Path, key_file: Path) -> None:
    reviews = [review(), review("add-two-numbers", hour=21)]
    guard = [accepted(), accepted("add-two-numbers")]
    ledger = home_with(tmp_path, reviews, guard)
    assert done_today(REVIEW, ledger, key_file, now=evening()) is True
    assert credit_units(REVIEW, ledger, key_file, DAY) == 2  # resolve pays it flat


def test_a_forged_row_pays_nothing(tmp_path: Path, key_file: Path) -> None:
    forged = sign({k: v for k, v in review().items() if k != "hmac"}, b"other-key")
    assert _done(tmp_path, key_file, [forged], [accepted()]) is False


def test_an_unsigned_row_pays_nothing(tmp_path: Path, key_file: Path) -> None:
    row = {k: v for k, v in review().items() if k != "hmac"}
    assert _done(tmp_path, key_file, [row], [accepted()]) is False


def test_another_source_pays_nothing(tmp_path: Path, key_file: Path) -> None:
    row = review(source="leetcode-coach")
    assert _done(tmp_path, key_file, [row], [accepted()]) is False


def test_no_accepted_submission_pays_nothing(tmp_path: Path, key_file: Path) -> None:
    assert _done(tmp_path, key_file, [review()], [accepted("other")]) is False


def test_a_forged_guard_row_does_not_back_it(tmp_path: Path, key_file: Path) -> None:
    fake = sign({k: v for k, v in accepted().items() if k != "hmac"}, b"x")
    assert _done(tmp_path, key_file, [review()], [fake]) is False


@pytest.mark.parametrize(
    ("entry", "extra"),
    [
        ("manual:2026-11-24", {}),
        ("manual_grant:two-sum", {}),
        (None, {"source": "manual_grant"}),
        (None, {"manual_grant": "ordered by hand"}),
    ],
)
def test_a_manual_grant_does_not_back_it(
    tmp_path: Path, key_file: Path, entry: str | None, extra: dict[str, object]
) -> None:
    guard = [accepted(entry=entry, **extra)]
    assert _done(tmp_path, key_file, [review()], guard) is False


def test_a_charge_row_does_not_back_it(tmp_path: Path, key_file: Path) -> None:
    row = {k: v for k, v in accepted().items() if k != "hmac"}
    charge = sign({**row, "kind": "charge"})
    assert _done(tmp_path, key_file, [review()], [charge]) is False


def test_a_submission_inside_the_lookback_backs_it(
    tmp_path: Path, key_file: Path
) -> None:
    old = DAY - timedelta(days=ACCEPTED_LOOKBACK_DAYS)
    assert _done(tmp_path, key_file, [review()], [accepted(day=old, hour=21)]) is True


def test_a_submission_older_than_the_lookback_pays_nothing(
    tmp_path: Path, key_file: Path
) -> None:
    old = DAY - timedelta(days=ACCEPTED_LOOKBACK_DAYS + 1)
    assert _done(tmp_path, key_file, [review()], [accepted(day=old)]) is False


def test_a_submission_after_the_review_pays_nothing(
    tmp_path: Path, key_file: Path
) -> None:
    assert _done(tmp_path, key_file, [review()], [accepted(hour=21)]) is False


def test_a_slug_pays_once_ever(tmp_path: Path, key_file: Path) -> None:
    earlier = review(day=DAY - timedelta(days=3))
    guard = [accepted(day=DAY - timedelta(days=4))]
    assert _done(tmp_path, key_file, [earlier, review()], guard) is False


def test_an_unpaid_first_review_still_spends_the_slug(
    tmp_path: Path, key_file: Path
) -> None:
    earlier = review(day=DAY - timedelta(days=20))
    assert _done(tmp_path, key_file, [review(), earlier], [accepted()]) is False


def test_a_review_of_another_day_pays_nothing(tmp_path: Path, key_file: Path) -> None:
    row = review(day=DAY - timedelta(days=1))
    assert _done(
        tmp_path, key_file, [row], [accepted(day=DAY - timedelta(days=1))]
    ) is (False)


def test_a_future_stamp_pays_nothing_today(tmp_path: Path, key_file: Path) -> None:
    assert _done(tmp_path, key_file, [review(hour=23)], [accepted()]) is False


def test_a_bad_stamp_pays_nothing_and_warns(
    tmp_path: Path, key_file: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    row = review(finished_at="soon")
    assert _done(tmp_path, key_file, [row], [accepted()]) is False
    assert "finished_at" in caplog.text


def test_a_missing_slug_pays_nothing_and_warns(
    tmp_path: Path, key_file: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    assert _done(tmp_path, key_file, [review(None)], [accepted()]) is False
    assert "title_slug" in caplog.text


def test_a_missing_guard_ledger_cannot_check(
    tmp_path: Path, key_file: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    assert _done(tmp_path, key_file, [review()], None) is None
    assert len(caplog.records) == 1
    assert "guard" in caplog.text


def test_an_unreadable_guard_ledger_cannot_check(
    tmp_path: Path, key_file: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    ledger = home_with(tmp_path, [review()], [])
    (tmp_path / GUARD_LEDGER).write_text("{not json", encoding="utf-8")
    assert done_today(REVIEW, ledger, key_file, now=evening()) is None
    assert len(caplog.records) == 1


def test_no_review_today_never_reads_the_guard(tmp_path: Path, key_file: Path) -> None:
    assert _done(tmp_path, key_file, [], None) is False


def test_a_missing_review_ledger_is_an_honest_no(
    tmp_path: Path, key_file: Path
) -> None:
    ledger = tmp_path / str(REVIEW.ledger)
    assert done_today(REVIEW, ledger, key_file, now=evening()) is False


def test_a_big_amount_still_pays_one_unit(tmp_path: Path, key_file: Path) -> None:
    row = {k: v for k, v in review().items() if k != "hmac"}
    ledger = home_with(tmp_path, [sign({**row, "amount": 1000})], [accepted()])
    assert credit_units(REVIEW, ledger, key_file, DAY) == 1
