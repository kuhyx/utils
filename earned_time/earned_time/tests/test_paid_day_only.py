# Copyright (c) 2026 Krzysztof Rudnicki
"""A LeetCode bonus needs the day paid in full, not one solve (0.18.0).

kuhy, 2026-10-24: Saturday cost 5 credits (4 + 1 debt), one problem was
solved, and both the +1 h shutdown and the +1 h gaming paid anyway. A credit
row is one unit of the day's price; only the signed ``charge`` leetcode-guard
writes once verified credits cover the price says the day was done.

On a day the gate stands down (a free day, or a sick day that does not keep
``leetcode``) there is no price and no charge, so one verified solve still
earns -- but only when the consumer says so live (``gate_off``). It is never
ledger state: a marker written during a two-minute sick claim would outlive
the claim being cleared.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import TYPE_CHECKING

import pytest

from earned_time import (
    LEETCODE,
    READING,
    credit_units,
    done_today,
    entry_signature,
    first_credit_at,
)

if TYPE_CHECKING:
    from pathlib import Path

KEY = b"test-key"
NOON = datetime(2026, 10, 24, 12, tzinfo=UTC)
TODAY = NOON.astimezone().date()
SOLVED_AT = NOON.timestamp() - 3600
CHARGED_AT = "2026-10-24T11:30:00+00:00"


def _signed(row: dict[str, object]) -> dict[str, object]:
    return {**row, "hmac": entry_signature(row, KEY)}


def _credit() -> dict[str, object]:
    return _signed(
        {
            "entry_id": "ac:1",
            "kind": "credit",
            "day": TODAY.isoformat(),
            "created_at": "2026-10-24T11:10:00+00:00",
            "amount": 1,
            "detail": {"source": "leetcode", "submitted_at": str(int(SOLVED_AT))},
        }
    )


def _charge(source: str = "leetcode") -> dict[str, object]:
    return _signed(
        {
            "entry_id": f"charge:{TODAY.isoformat()}",
            "kind": "charge",
            "day": TODAY.isoformat(),
            "created_at": CHARGED_AT,
            "amount": 5,
            "detail": {"source": source},
        }
    )


@pytest.fixture
def key_file(tmp_path: Path) -> Path:
    path = tmp_path / "hmac.key"
    path.write_bytes(KEY)
    return path


def _ledger(tmp_path: Path, rows: list[object]) -> Path:
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps({"entries": rows}), encoding="utf-8")
    return path


def test_one_solve_on_an_unpaid_day_earns_nothing(
    tmp_path: Path, key_file: Path
) -> None:
    path = _ledger(tmp_path, [_credit()])
    assert done_today(LEETCODE, path, key_file, now=NOON) is False
    assert first_credit_at(LEETCODE, path, key_file, TODAY) is None
    assert credit_units(LEETCODE, path, key_file, TODAY) == 0


def test_the_paid_day_earns_from_its_charge(tmp_path: Path, key_file: Path) -> None:
    path = _ledger(tmp_path, [_credit(), _charge()])
    assert done_today(LEETCODE, path, key_file, now=NOON) is True
    expected = datetime.fromisoformat(CHARGED_AT).timestamp()
    assert first_credit_at(LEETCODE, path, key_file, TODAY) == expected


@pytest.mark.parametrize("source", ["escape", "leetcode-outage"])
def test_a_forgiven_day_earns_nothing_even_with_a_solve(
    tmp_path: Path, key_file: Path, source: str
) -> None:
    path = _ledger(tmp_path, [_credit(), _charge(source)])
    assert done_today(LEETCODE, path, key_file, now=NOON) is False


def test_a_solve_earns_while_the_gate_is_off(tmp_path: Path, key_file: Path) -> None:
    path = _ledger(tmp_path, [_credit()])
    assert done_today(LEETCODE, path, key_file, now=NOON, gate_off=True) is True
    assert first_credit_at(LEETCODE, path, key_file, TODAY, gate_off=True) == (
        SOLVED_AT
    )
    assert credit_units(LEETCODE, path, key_file, TODAY, gate_off=True) == 1


def test_the_gate_being_off_is_not_a_solve(tmp_path: Path, key_file: Path) -> None:
    path = _ledger(tmp_path, [_charge("escape")])
    assert done_today(LEETCODE, path, key_file, now=NOON, gate_off=True) is False


def test_gate_off_changes_nothing_for_other_earners(
    tmp_path: Path, key_file: Path
) -> None:
    path = _ledger(tmp_path, [_charge()])
    assert done_today(READING, path, key_file, now=NOON, gate_off=True) is False
