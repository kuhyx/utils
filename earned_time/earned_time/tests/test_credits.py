# Copyright (c) 2026 Krzysztof Rudnicki
"""Day-scoped ledger reads (first credit, units) and the workout's credit rule."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
import json
import logging
from typing import TYPE_CHECKING

import pytest

from earned_time import (
    ANKI,
    LEETCODE,
    WORKOUT,
    Earner,
    credit_units,
    day_window,
    entry_signature,
    first_credit_at,
)
from earned_time._credits import credit_time

if TYPE_CHECKING:
    from pathlib import Path

KEY = b"test-key"
DAY = date(2026, 10, 10)
START, END = day_window(DAY)


def _at(hour: int, minute: int = 0, day: date = DAY) -> float:
    return datetime.combine(day, time(hour, minute)).astimezone().timestamp()


def _signed(row: dict[str, object]) -> dict[str, object]:
    return {**row, "hmac": entry_signature(row, KEY)}


def _workout(entry: str, done: float) -> dict[str, object]:
    detail = {"completed_at": str(done), "source": "runnerup_tcx"}
    row = {"kind": "credit", "entry_id": entry, "day": "", "detail": detail}
    return _signed(row)


def _rest(entry: str, day: date, declared: object) -> dict[str, object]:
    detail: dict[str, object] = {
        "completed_at": str(_at(0, 0, day)),
        "source": "rest_day",
    }
    if declared is not None:
        detail["declared_at"] = declared
    row = {
        "kind": "credit",
        "entry_id": entry,
        "day": day.isoformat(),
        "detail": detail,
    }
    return _signed(row)


@pytest.fixture
def key_file(tmp_path: Path) -> Path:
    path = tmp_path / "hmac.key"
    path.write_bytes(KEY)
    return path


def _ledger(tmp_path: Path, rows: list[object]) -> Path:
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps({"entries": rows}), encoding="utf-8")
    return path


def test_day_window_spans_the_local_day() -> None:
    assert _at(0) == START
    next_midnight = datetime.combine(DAY + timedelta(days=1), time.min).astimezone()
    assert next_midnight.timestamp() - 1 < END < next_midnight.timestamp()


def test_units_and_first_credit(tmp_path: Path, key_file: Path) -> None:
    rows: list[object] = [
        _workout("evening", _at(18)),
        _workout("morning", _at(8, 15)),
        _workout("yesterday", _at(23, 0, DAY - timedelta(days=1))),
        {**_workout("forged", _at(6)), "hmac": "forged"},
        "junk",
    ]
    path = _ledger(tmp_path, rows)
    assert credit_units(WORKOUT, path, key_file, DAY) == 2
    assert first_credit_at(WORKOUT, path, key_file, DAY) == _at(8, 15)
    later = DAY + timedelta(days=1)
    assert credit_units(WORKOUT, path, key_file, later) == 0
    assert first_credit_at(WORKOUT, path, key_file, later) is None


def test_missing_workout_ledger_is_zero_units(tmp_path: Path, key_file: Path) -> None:
    assert credit_units(WORKOUT, tmp_path / "none.json", key_file, DAY) == 0


def test_cannot_check_is_none(tmp_path: Path, key_file: Path) -> None:
    path = _ledger(tmp_path, [_workout("a", _at(9))])
    assert credit_units(WORKOUT, path, tmp_path / "nokey", DAY) is None
    assert first_credit_at(WORKOUT, path, tmp_path / "nokey", DAY) is None
    assert first_credit_at(LEETCODE, tmp_path / "none.json", key_file, DAY) is None


def test_earner_without_reader_is_refused(tmp_path: Path, key_file: Path) -> None:
    bare = Earner(name="bare", label="bare", gaming_minutes=0, shutdown_minutes=0)
    with pytest.raises(ValueError, match="no shared reader"):
        credit_units(bare, tmp_path / "x.json", key_file, DAY)
    with pytest.raises(ValueError, match="no shared reader"):
        first_credit_at(bare, tmp_path / "x.json", key_file, DAY)


def test_credit_time_prefers_the_earners_stamp() -> None:
    row: dict[str, object] = {
        "created_at": "2026-10-10T20:27:00+02:00",
        "detail": {"submitted_at": "1791484015"},
    }
    assert credit_time(LEETCODE, row) == 1791484015.0
    created = datetime.fromisoformat("2026-10-10T20:27:00+02:00").timestamp()
    assert credit_time(ANKI, row) == created
    assert credit_time(LEETCODE, {**row, "detail": {"submitted_at": "?"}}) == created
    assert credit_time(LEETCODE, {**row, "detail": "nope"}) == created


def test_credit_time_without_a_matcher_uses_created_at() -> None:
    bare = Earner(name="bare", label="bare", gaming_minutes=0, shutdown_minutes=0)
    row: dict[str, object] = {"created_at": "2026-10-10T08:00:00+00:00"}
    assert (
        credit_time(bare, row)
        == datetime.fromisoformat("2026-10-10T08:00:00+00:00").timestamp()
    )


def test_credit_time_unusable_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        assert credit_time(ANKI, {"entry_id": "x", "created_at": "never"}) is None
    assert "no usable time" in caplog.text


def test_first_credit_skips_rows_without_a_time(tmp_path: Path, key_file: Path) -> None:
    row = _signed({"kind": "credit", "detail": {"anki_day": DAY.isoformat()}})
    assert first_credit_at(ANKI, _ledger(tmp_path, [row]), key_file, DAY) is None


def _match(row: dict[str, object]) -> bool:
    assert WORKOUT.match is not None
    return WORKOUT.match(row, (START, END))


@pytest.mark.parametrize(
    ("detail", "expected"),
    [
        ({"completed_at": str(_at(12))}, True),
        ({"completed_at": str(START - 1)}, False),
        ("not a dict", False),
    ],
)
def test_workout_match(detail: object, *, expected: bool) -> None:
    assert _match({"detail": detail}) is expected


def test_workout_without_completion_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        assert not _match({"entry_id": "w", "detail": {"source": "runnerup_tcx"}})
    assert "no usable completed_at" in caplog.text


def test_rest_day_declared_the_evening_before_counts() -> None:
    assert _match(_rest("r", DAY, str(START - 3600)))


def test_rest_day_for_another_day_does_not_count(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        assert not _match(_rest("r", DAY + timedelta(days=1), str(START - 3600)))
    assert not caplog.text


@pytest.mark.parametrize("declared", [str(_at(9)), str(START), "soon", None])
def test_rest_day_not_declared_before_its_day_does_not_count(
    caplog: pytest.LogCaptureFixture, declared: object
) -> None:
    with caplog.at_level(logging.WARNING):
        assert not _match(_rest("r", DAY, declared))
    assert "not declared before its day" in caplog.text


def test_rest_day_unit_via_the_ledger(tmp_path: Path, key_file: Path) -> None:
    rows: list[object] = [
        _rest("ok", DAY, str(START - 60)),
        _rest("same-day", DAY + timedelta(days=1), str(_at(9, 0, DAY + timedelta(1)))),
    ]
    path = _ledger(tmp_path, rows)
    assert credit_units(WORKOUT, path, key_file, DAY) == 1
    assert credit_units(WORKOUT, path, key_file, DAY + timedelta(days=1)) == 0
