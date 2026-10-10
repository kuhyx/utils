# Copyright (c) 2026 Krzysztof Rudnicki
"""The tutor ledger: which signed 0.7.0 block rows count, and how many minutes."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
import json
from typing import TYPE_CHECKING

import pytest

from earned_time import (
    AUTOMATION_TUTOR,
    credit_units,
    day_window,
    entry_signature,
    first_credit_at,
)
from earned_time._match import tutor_match

if TYPE_CHECKING:
    from pathlib import Path

KEY = b"test-key"
DAY = date(2026, 10, 12)
WINDOW = day_window(DAY)


def _at(hour: int, minute: int = 0, day: date = DAY) -> float:
    return datetime.combine(day, time(hour, minute)).astimezone().timestamp()


def block(session: str, number: int, ended: object) -> dict[str, object]:
    """One signed row in the contract the tutor writes."""
    row: dict[str, object] = {
        "kind": "credit",
        "entry_id": f"{session}-b{number}",
        "day": DAY.isoformat(),
        "created_at": _at(23, 59),
        "detail": {
            "session_id": session,
            "block": number,
            "active_seconds": 900,
            "ended_at": ended,
            "checks_passed": 3,
            "checks_total": 3,
        },
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


def test_match_by_ended_at() -> None:
    assert tutor_match(block("s", 1, _at(18, 15)), WINDOW)
    yesterday = _at(23, 50, DAY - timedelta(days=1))
    assert not tutor_match(block("s", 1, yesterday), WINDOW)


@pytest.mark.parametrize("ended", [None, "soon"])
def test_unusable_ended_at_never_counts(
    ended: object, caplog: pytest.LogCaptureFixture
) -> None:
    assert not tutor_match(block("s", 1, ended), WINDOW)
    assert "no usable ended_at" in caplog.text


def test_row_without_detail_never_counts() -> None:
    assert not tutor_match({"kind": "credit", "entry_id": "x"}, WINDOW)


def test_legacy_blocks_count_15_once_and_skip_forgeries(
    tmp_path: Path, key_file: Path
) -> None:
    tampered = block("s1", 3, _at(19))
    detail = tampered["detail"]
    assert isinstance(detail, dict)
    tampered["detail"] = {**detail, "active_seconds": 9000}
    rows: list[object] = [
        block("s1", 1, _at(18, 15)),
        block("s1", 2, _at(18, 30)),
        block("s1", 2, _at(18, 30)),  # the same block written twice
        tampered,
        block("s0", 1, _at(23, 0, DAY - timedelta(days=1))),
    ]
    path = _ledger(tmp_path, rows)
    # 0.7.0 block rows carry no detail.minutes: each pays 15 minutes.
    assert credit_units(AUTOMATION_TUTOR, path, key_file, DAY) == 30
    assert first_credit_at(AUTOMATION_TUTOR, path, key_file, DAY) == _at(18, 15)


def test_rows_without_entry_id_each_count(tmp_path: Path, key_file: Path) -> None:
    rows: list[object] = []
    for number in (1, 2):
        row = {k: v for k, v in block("s", number, _at(9)).items() if k != "hmac"}
        del row["entry_id"]
        rows.append({**row, "hmac": entry_signature(row, KEY)})
    path = _ledger(tmp_path, rows)
    assert credit_units(AUTOMATION_TUTOR, path, key_file, DAY) == 30


def test_missing_tutor_ledger_is_zero(tmp_path: Path, key_file: Path) -> None:
    assert credit_units(AUTOMATION_TUTOR, tmp_path / "no.json", key_file, DAY) == 0
