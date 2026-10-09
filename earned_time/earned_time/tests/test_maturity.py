# Copyright (c) 2026 Krzysztof Rudnicki
"""The maturity levels, the counts behind them and the penalty reasons."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from typing import TYPE_CHECKING

import pytest

from earned_time import (
    LEETCODE,
    MATURE_MIN_AGE_DAYS,
    MATURE_MIN_CREDIT_DAYS,
    READING,
    Earner,
    maturity,
)
from earned_time._evidence import credit_day
from earned_time.tests._maturity_rows import (
    TODAY,
    at,
    days,
    ledger_file,
    signed,
    solve,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_an_earner_without_a_matcher_raises(tmp_path: Path, key_file: Path) -> None:
    bare = Earner(name="x", label="x", gaming_minutes=1, shutdown_minutes=1)
    with pytest.raises(ValueError, match="no shared reader"):
        maturity(bare, tmp_path / "none.json", key_file, TODAY)
    with pytest.raises(ValueError, match="no shared reader"):
        credit_day(bare, {})


def test_mature_at_the_thresholds(tmp_path: Path, key_file: Path) -> None:
    first = TODAY - timedelta(days=MATURE_MIN_AGE_DAYS)
    ledger = ledger_file(tmp_path, days(first, MATURE_MIN_CREDIT_DAYS))
    verdict = maturity(LEETCODE, ledger, key_file, TODAY)
    assert verdict.level == "mature"
    assert verdict.credit_days == MATURE_MIN_CREDIT_DAYS
    assert verdict.first_credit == first
    assert verdict.checked
    assert verdict.reasons[-1] == "no penalty_from: a pure bonus"


@pytest.mark.parametrize(
    ("age", "count"),
    [
        (MATURE_MIN_AGE_DAYS - 1, MATURE_MIN_CREDIT_DAYS),
        (MATURE_MIN_AGE_DAYS + 10, MATURE_MIN_CREDIT_DAYS - 1),
    ],
)
def test_maturing_below_either_threshold(
    tmp_path: Path, key_file: Path, age: int, count: int
) -> None:
    ledger = ledger_file(tmp_path, days(TODAY - timedelta(days=age), count))
    verdict = maturity(LEETCODE, ledger, key_file, TODAY)
    assert verdict.level == "maturing"
    assert verdict.reasons[0].startswith(f"{count}/{MATURE_MIN_CREDIT_DAYS} credit")


def test_unconfirmed_gate_stays_new(tmp_path: Path, key_file: Path) -> None:
    ledger = ledger_file(tmp_path, days(TODAY - timedelta(days=60), 40))
    verdict = maturity(replace(LEETCODE, confirmed_on=None), ledger, key_file, TODAY)
    assert verdict.level == "new"
    assert "no confirmed_on" in verdict.reasons[0]
    assert verdict.credit_days == 40


def test_counts_skip_future_replayed_and_unmatched_rows(
    tmp_path: Path, key_file: Path
) -> None:
    rows: list[object] = [
        solve(TODAY),
        solve(TODAY),  # replayed: same entry_id
        solve(TODAY + timedelta(days=1)),  # after the verdict's day
        solve(TODAY, entry="ac:other"),
        signed({"kind": "credit", "detail": {"submitted_at": at(TODAY)}}),
        signed({"kind": "credit", "detail": {"submitted_at": at(TODAY)}}),
        signed({"kind": "credit", "entry_id": "no-day", "detail": {}}),
    ]
    verdict = maturity(LEETCODE, ledger_file(tmp_path, rows), key_file, TODAY)
    assert (verdict.credit_rows, verdict.credit_days) == (4, 1)
    assert verdict.first_credit == verdict.last_credit == TODAY


def test_penalty_reasons(tmp_path: Path, key_file: Path) -> None:
    early = replace(
        READING,
        penalty_from=date(2026, 10, 5),
        confirmed_on=date(2026, 10, 1),
    )
    first = date(2026, 10, 2)
    row = signed(
        {
            "kind": "credit",
            "entry_id": "session:a",
            "amount": 44,
            "detail": {"bonus": "1", "ended_at": at(first)},
        }
    )
    ledger = ledger_file(tmp_path, [row])
    on_time = maturity(early, ledger, key_file, TODAY)
    assert on_time.penalty_start == early.penalty_from
    assert on_time.reasons[-1] == "penalty from 2026-10-05, as registered"
    late = maturity(READING, ledger, key_file, TODAY)
    assert late.penalty_start == date(2026, 10, 3)
    assert late.reasons[-1] == "penalty delayed from 2026-10-01 to 2026-10-03"


def test_today_defaults_to_now(tmp_path: Path, key_file: Path) -> None:
    verdict = maturity(READING, tmp_path / "missing.json", key_file)
    assert verdict.level == "new"
