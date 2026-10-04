# Copyright (c) 2026 Krzysztof Rudnicki
"""The shared ledger reader, and every way it refuses to answer."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import logging
from typing import TYPE_CHECKING

import pytest

from earned_time import LEETCODE, READING, WORKOUT, done_today, entry_signature
from earned_time._ledger import read_key, read_rows, today_window, verified

if TYPE_CHECKING:
    from pathlib import Path

KEY = b"test-key"
NOON = datetime(2026, 10, 4, 12, tzinfo=UTC)
INSIDE = today_window(NOON)[1] - 60


def _signed(row: dict[str, object]) -> dict[str, object]:
    return {**row, "hmac": entry_signature(row, KEY)}


@pytest.fixture
def key_file(tmp_path: Path) -> Path:
    path = tmp_path / "hmac.key"
    path.write_bytes(KEY + b"\n")
    return path


def _ledger(tmp_path: Path, rows: list[object]) -> Path:
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps({"entries": rows}), encoding="utf-8")
    return path


def test_signature_is_gatelocks_canonical_form() -> None:
    # Pinned vector: sorted keys, compact separators, hmac field excluded --
    # gatelock's log_integrity.compute_entry_hmac gives the same digest.
    row = {"b": 1, "a": "x", "hmac": "ignored"}
    assert entry_signature(row, b"k") == (
        "5fd4480841273ec8336e76e19bbeb1dd7bd9ded2c442c84cdb2786f7e030987b"
    )


def test_verified() -> None:
    row = _signed({"kind": "credit"})
    assert verified(row, KEY)
    assert not verified({**row, "kind": "charge"}, KEY)
    assert not verified({"kind": "credit"}, KEY)


def test_today_window_defaults_to_now() -> None:
    start, end = today_window()
    assert start <= end


def test_read_key(tmp_path: Path, key_file: Path) -> None:
    assert read_key(key_file) == KEY
    assert read_key(tmp_path / "missing") is None
    empty = tmp_path / "empty"
    empty.write_bytes(b"  \n")
    assert read_key(empty) is None


def test_missing_ledger_is_no_only_where_declared(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    assert read_rows(missing, READING) == []
    assert read_rows(missing, LEETCODE) is None


@pytest.mark.parametrize(
    ("content", "message"),
    [("{not json", "not valid JSON"), ('{"entries": 3}', "no entries array")],
)
def test_unusable_ledger(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, content: str, message: str
) -> None:
    path = tmp_path / "ledger.json"
    path.write_text(content, encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert read_rows(path, READING) is None
    assert message in caplog.text


def test_unreadable_ledger(tmp_path: Path) -> None:
    assert read_rows(tmp_path, READING) is None  # a directory


def test_done_today(tmp_path: Path, key_file: Path) -> None:
    good = _signed({"kind": "credit", "detail": {"submitted_at": INSIDE}})
    path = _ledger(tmp_path, [good])
    assert done_today(LEETCODE, path, key_file, now=NOON) is True


def test_not_done_today(tmp_path: Path, key_file: Path) -> None:
    rows: list[object] = [
        "junk",
        _signed({"kind": "charge", "detail": {"submitted_at": INSIDE}}),
        {"kind": "credit", "detail": {"submitted_at": INSIDE}, "hmac": "forged"},
    ]
    path = _ledger(tmp_path, rows)
    assert done_today(LEETCODE, path, key_file, now=NOON) is False


def test_cannot_check(tmp_path: Path, key_file: Path) -> None:
    path = _ledger(tmp_path, [])
    assert done_today(LEETCODE, path, tmp_path / "nokey") is None
    assert done_today(LEETCODE, tmp_path / "missing.json", key_file) is None


def test_earner_without_reader_is_refused(tmp_path: Path, key_file: Path) -> None:
    with pytest.raises(ValueError, match="no shared reader"):
        done_today(WORKOUT, tmp_path / "x.json", key_file)
