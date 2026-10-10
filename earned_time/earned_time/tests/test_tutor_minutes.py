# Copyright (c) 2026 Krzysztof Rudnicki
"""0.8.0: tutor rows pay ``detail.minutes``; 0.7.0 block rows still pay 15."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from earned_time import (
    AUTOMATION_TUTOR,
    WORKOUT,
    credit_units,
    entry_signature,
    first_credit_at,
    resolve,
)
from earned_time._credits import row_units
from earned_time._match import LEGACY_TUTOR_MINUTES, tutor_match, tutor_minutes
from earned_time.tests.test_tutor_ledger import DAY, KEY, WINDOW, _at, _ledger, block

if TYPE_CHECKING:
    from pathlib import Path

OTHERS = {"workout": 1, "leetcode": 1, "reading": 1}


def minute(
    session: str, first: int, ended: float, minutes: object = 1
) -> dict[str, object]:
    """A signed 0.8.0 row: ``minutes`` active minutes from the session's ``first``."""
    row: dict[str, object] = {
        "kind": "credit",
        "entry_id": f"{session}-m{first}",
        "day": DAY.isoformat(),
        "created_at": ended,
        "detail": {"session_id": session, "minutes": minutes, "ended_at": ended},
    }
    return {**row, "hmac": entry_signature(row, KEY)}


@pytest.fixture
def key_file(tmp_path: Path) -> Path:
    path = tmp_path / "hmac.key"
    path.write_bytes(KEY)
    return path


def _units(tmp_path: Path, key_file: Path, rows: list[object]) -> int | None:
    return credit_units(AUTOMATION_TUTOR, _ledger(tmp_path, rows), key_file, DAY)


def test_minute_rows_sum(tmp_path: Path, key_file: Path) -> None:
    rows: list[object] = [minute("s", n, _at(18, n)) for n in (1, 2, 3)]
    rows.append(minute("s", 4, _at(18, 13), minutes=10))
    assert _units(tmp_path, key_file, rows) == 13
    assert first_credit_at(
        AUTOMATION_TUTOR, _ledger(tmp_path, rows), key_file, DAY
    ) == _at(18, 1)


def test_legacy_rows_count_15() -> None:
    assert tutor_minutes(block("s", 1, _at(9))) == LEGACY_TUTOR_MINUTES == 15
    assert tutor_minutes({"kind": "credit"}) == 15  # no detail: legacy shape


def test_mixed_day_sums_blocks_and_minutes(tmp_path: Path, key_file: Path) -> None:
    rows: list[object] = [block("old", 1, _at(15, 0))]
    rows += [minute("new", n, _at(18, n)) for n in range(1, 21)]
    units = _units(tmp_path, key_file, rows)
    assert units == 35
    day = resolve({**OTHERS, "automation": units or 0}, DAY)
    assert (day.gaming_minutes, day.shutdown_minutes) == (420 + 35, 22 * 60 + 35)


def test_the_day_caps_at_60_across_sessions(tmp_path: Path, key_file: Path) -> None:
    rows: list[object] = [block("a", n, _at(9, 15 * n)) for n in (1, 2, 3)]
    rows += [minute("b", n, _at(14, n)) for n in range(1, 21)]
    units = _units(tmp_path, key_file, rows)
    assert units == 65  # the raw sum; resolve applies max_units
    term = resolve({"automation": units}, DAY).term("automation")
    assert (term.gaming_minutes, term.shutdown_minutes) == (60, 60)


def test_a_replayed_entry_id_pays_once_and_never_more(
    tmp_path: Path, key_file: Path
) -> None:
    rows: list[object] = [
        minute("s", 1, _at(18, 1)),
        minute("s", 1, _at(18, 1)),  # the same minute written twice
        minute("s", 2, _at(18, 6), minutes=5),
        minute("s", 2, _at(18, 6), minutes=1),  # a rewrite: the smaller pays
        minute("s", 3, _at(18, 9), minutes=2),
        minute("s", 3, _at(18, 9), minutes=9),
    ]
    assert _units(tmp_path, key_file, rows) == 1 + 1 + 2


@pytest.mark.parametrize("bad", [0, -1, True, 1.5, "5", None])
def test_bad_minutes_never_count(
    bad: object, tmp_path: Path, key_file: Path, caplog: pytest.LogCaptureFixture
) -> None:
    row = minute("s", 1, _at(18), minutes=bad)
    assert tutor_minutes(row) is None
    assert not tutor_match(row, WINDOW)
    assert "bad minutes" in caplog.text
    assert row_units(AUTOMATION_TUTOR, row) == 0
    assert _units(tmp_path, key_file, [row, minute("s", 2, _at(18, 1))]) == 1


def test_other_earners_pay_one_unit_per_row() -> None:
    assert row_units(WORKOUT, {"detail": {"minutes": 40}}) == 1


@pytest.mark.parametrize("blocks", range(7))
def test_an_all_legacy_day_resolves_as_0_7_0_did(
    blocks: int, tmp_path: Path, key_file: Path
) -> None:
    # 0.7.0: min(blocks, 4) x 15 gaming and 15 shutdown; 0.8.0: min(15n, 60).
    rows: list[object] = [block("s", n, _at(9, 5 * n)) for n in range(1, blocks + 1)]
    units = _units(tmp_path, key_file, rows) or 0
    paid = 15 * min(blocks, 4)
    for others in ({}, OTHERS):
        day = resolve({**others, "automation": units}, DAY)
        base = 420 if others else 180
        floor = 22 * 60 if others else 18 * 60 + 50
        assert (day.gaming_minutes, day.shutdown_minutes) == (
            base + paid,
            floor + paid,
        )
