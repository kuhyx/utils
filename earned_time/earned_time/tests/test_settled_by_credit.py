# Copyright (c) 2026 Krzysztof Rudnicki
"""A LeetCode day settled from banked credits earns the bonus like a solve.

kuhy, 2026-10-23: five solves on 10-22 paid 10-23's gate in advance, and the
bonus (gaming, leisure, shutdown) still said "no solve today" -- the system
punished working ahead. A signed ``charge`` with ``source == "leetcode"`` is
written only when verified credits cover the day (leetcode-guard
``_gate.decide``); the escape hatch and the outage path write their own
sources and must never pay.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
import json
from typing import TYPE_CHECKING

import pytest

from earned_time import (
    LEETCODE,
    READING,
    done_today,
    entry_signature,
    first_credit_at,
)

if TYPE_CHECKING:
    from pathlib import Path

KEY = b"test-key"
NOON = datetime(2026, 10, 23, 12, tzinfo=UTC)
TODAY = NOON.astimezone().date()
CHARGED_AT = "2026-10-23T09:00:00+00:00"


def _charge(day: str, source: str = "leetcode") -> dict[str, object]:
    row: dict[str, object] = {
        "entry_id": f"charge:{day}",
        "kind": "charge",
        "day": day,
        "created_at": CHARGED_AT,
        "amount": 4,
        "detail": {"source": source},
    }
    return {**row, "hmac": entry_signature(row, KEY)}


@pytest.fixture
def key_file(tmp_path: Path) -> Path:
    path = tmp_path / "hmac.key"
    path.write_bytes(KEY)
    return path


def _ledger(tmp_path: Path, rows: list[object]) -> Path:
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps({"entries": rows}), encoding="utf-8")
    return path


def test_a_day_paid_from_banked_credits_counts(tmp_path: Path, key_file: Path) -> None:
    path = _ledger(tmp_path, [_charge(TODAY.isoformat())])
    assert done_today(LEETCODE, path, key_file, now=NOON) is True


@pytest.mark.parametrize("source", ["escape", "leetcode-outage", "seed"])
def test_a_forgiven_day_never_counts(
    tmp_path: Path, key_file: Path, source: str
) -> None:
    path = _ledger(tmp_path, [_charge(TODAY.isoformat(), source)])
    assert done_today(LEETCODE, path, key_file, now=NOON) is False


def test_a_forged_charge_never_counts(tmp_path: Path, key_file: Path) -> None:
    forged = {**_charge(TODAY.isoformat()), "hmac": "forged"}
    path = _ledger(tmp_path, [forged])
    assert done_today(LEETCODE, path, key_file, now=NOON) is False


def test_yesterdays_charge_pays_yesterday_only(tmp_path: Path, key_file: Path) -> None:
    path = _ledger(tmp_path, [_charge("2026-10-22")])
    assert done_today(LEETCODE, path, key_file, now=NOON) is False


def test_only_leetcode_reads_charges(tmp_path: Path, key_file: Path) -> None:
    path = _ledger(tmp_path, [_charge(TODAY.isoformat())])
    assert done_today(READING, path, key_file, now=NOON) is False


def test_the_settling_charge_is_timed_at_its_writing(
    tmp_path: Path, key_file: Path
) -> None:
    path = _ledger(tmp_path, [_charge(TODAY.isoformat())])
    expected = datetime.fromisoformat(CHARGED_AT).timestamp()
    assert first_credit_at(LEETCODE, path, key_file, TODAY) == expected
    assert first_credit_at(LEETCODE, path, key_file, date(2026, 10, 22)) is None
