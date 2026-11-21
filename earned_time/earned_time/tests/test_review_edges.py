# Copyright (c) 2026 Krzysztof Rudnicki
"""Review evidence edges (0.23.0): odd rows on either ledger."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from earned_time import (
    GUARD_LEDGER,
    REVIEW,
    day_window,
    done_today,
    guard_ledger_for,
    review_match,
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


def _unsigned(row: dict[str, object]) -> dict[str, object]:
    return {k: v for k, v in row.items() if k != "hmac"}


def test_the_matcher_wants_the_coach_source() -> None:
    assert review_match(accepted(), day_window(DAY)) is False
    assert review_match(review(), day_window(DAY)) is True


def test_a_guard_row_of_another_source_does_not_back_it(
    tmp_path: Path, key_file: Path
) -> None:
    ledger = home_with(tmp_path, [review()], [accepted(source="escape")])
    assert done_today(REVIEW, ledger, key_file, now=evening()) is False


def test_a_guard_row_without_a_stamp_does_not_back_it(
    tmp_path: Path, key_file: Path
) -> None:
    ledger = home_with(tmp_path, [review()], [accepted(submitted_at="later")])
    assert done_today(REVIEW, ledger, key_file, now=evening()) is False


def test_junk_guard_rows_are_skipped(tmp_path: Path, key_file: Path) -> None:
    ledger = home_with(tmp_path, [review()], [])
    guard = {"entries": ["junk", accepted()]}
    (tmp_path / GUARD_LEDGER).write_text(json.dumps(guard), encoding="utf-8")
    assert done_today(REVIEW, ledger, key_file, now=evening()) is True


def test_a_timeless_review_never_spends_the_slug(
    tmp_path: Path, key_file: Path
) -> None:
    timeless = sign({**_unsigned(review(finished_at="x")), "created_at": "never"})
    ledger = home_with(tmp_path, [timeless, review()], [accepted()])
    assert done_today(REVIEW, ledger, key_file, now=evening()) is True


def test_junk_review_rows_are_skipped(tmp_path: Path, key_file: Path) -> None:
    ledger = home_with(tmp_path, [review()], [accepted()])
    text = ledger.read_text(encoding="utf-8").replace('"entries": [', '"entries": [7, ')
    ledger.write_text(text, encoding="utf-8")
    assert done_today(REVIEW, ledger, key_file, now=evening()) is True


def test_the_guard_ledger_shares_the_review_ledgers_home(tmp_path: Path) -> None:
    review_ledger = tmp_path / str(REVIEW.ledger)
    assert guard_ledger_for(review_ledger, REVIEW) == tmp_path / GUARD_LEDGER
