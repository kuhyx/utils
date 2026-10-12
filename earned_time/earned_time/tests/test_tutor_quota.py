# Copyright (c) 2026 Krzysztof Rudnicki
"""The tutor's weekday quota (0.10.0): fewer minutes for the same full reward."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
import json
from typing import TYPE_CHECKING

import pytest

from earned_time import (
    TUTOR,
    TUTOR_QUOTA_FROM,
    TUTOR_QUOTA_MINUTES,
    credit_units,
    entry_signature,
    resolve,
    tutor_quota_for,
)
from earned_time._quota import EDGE_DAYS, WEEKEND, WORKDAYS, tutor_day_units

if TYPE_CHECKING:
    from pathlib import Path

KEY = b"quota-key"
EVE = date(2026, 10, 11)  # Sunday, the day before the switch
MON, TUE, WED, THU, FRI, SAT, SUN = (
    TUTOR_QUOTA_FROM + timedelta(days=n) for n in range(7)
)


def _at(day: date, minute: int) -> float:
    start = datetime.combine(day, time(17)).astimezone()
    return (start + timedelta(minutes=minute)).timestamp()


def _row(day: date, entry: str, ended: float, minutes: int | None) -> dict[str, object]:
    detail: dict[str, object] = {"ended_at": ended}
    if minutes is not None:
        detail["minutes"] = minutes
    row: dict[str, object] = {
        "kind": "credit",
        "entry_id": entry,
        "day": day.isoformat(),
        "created_at": ended,
        "detail": detail,
    }
    return {**row, "hmac": entry_signature(row, KEY)}


def _units(tmp_path: Path, day: date, rows: list[dict[str, object]]) -> int | None:
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps({"entries": rows}), encoding="utf-8")
    key = tmp_path / "hmac.key"
    key.write_bytes(KEY)
    return credit_units(TUTOR, ledger, key, day)


def _minutes(day: date, count: int) -> list[dict[str, object]]:
    return [_row(day, f"s-m{n}", _at(day, n), 1) for n in range(1, count + 1)]


def test_weekday_classes_partition_the_week() -> None:
    assert frozenset(range(7)) == WORKDAYS | EDGE_DAYS | WEEKEND
    assert len(WORKDAYS) + len(EDGE_DAYS) + len(WEEKEND) == 7
    assert set(TUTOR_QUOTA_MINUTES) == {WORKDAYS, EDGE_DAYS, WEEKEND}


def test_workdays_match_freedays() -> None:
    freedays = pytest.importorskip("freedays")
    assert freedays.WORKDAYS == WORKDAYS


@pytest.mark.parametrize(
    ("day", "quota"),
    [(MON, 30), (TUE, 15), (WED, 15), (THU, 15), (FRI, 30), (SAT, 50), (SUN, 50)],
)
def test_quota_per_weekday(day: date, quota: int) -> None:
    assert tutor_quota_for(day) == quota


def test_no_quota_before_the_switch() -> None:
    assert date(2026, 10, 12) == MON
    assert tutor_quota_for(EVE) is None


@pytest.mark.parametrize(
    ("day", "minutes", "units"),
    [
        (EVE, 10, 10),
        (EVE, 50, 50),
        (MON, 10, 20),
        (MON, 15, 30),
        (MON, 30, 60),
        (TUE, 10, 40),
        (TUE, 15, 60),
        (SAT, 10, 12),
        (SAT, 25, 30),
        (SAT, 50, 60),
        (SAT, 7, 8),  # 7 * 60 / 50 = 8.4, floored
        (FRI, 1, 2),
    ],
)
def test_one_minute_rows_scale_to_the_quota(
    tmp_path: Path, day: date, minutes: int, units: int
) -> None:
    assert _units(tmp_path, day, _minutes(day, minutes)) == units


@pytest.mark.parametrize("day", [MON, TUE, SAT])
def test_the_day_caps_at_60(tmp_path: Path, day: date) -> None:
    assert _units(tmp_path, day, _minutes(day, 90)) == 60


def test_before_the_switch_minutes_pass_through_uncapped(tmp_path: Path) -> None:
    assert _units(tmp_path, EVE, _minutes(EVE, 90)) == 90


def test_multi_row_day_scales_the_sum_not_each_row(tmp_path: Path) -> None:
    # Per row: 3 * 60 // 50 = 3 each, 5 rows = 15. On the sum: 15 * 60 // 50 = 18.
    rows = [_row(SAT, f"s{n}-m1", _at(SAT, 10 * n), 3) for n in range(5)]
    assert _units(tmp_path, SAT, rows) == 18


def test_a_replayed_row_still_pays_once(tmp_path: Path) -> None:
    rows = [_row(TUE, "s-m1", _at(TUE, 1), 5), _row(TUE, "s-m1", _at(TUE, 2), 5)]
    assert _units(tmp_path, TUE, rows) == 20


def test_legacy_block_rows_count_15_minutes_then_scale(tmp_path: Path) -> None:
    blocks = [_row(MON, "s-b1", _at(MON, 15), None)]
    assert _units(tmp_path, MON, blocks) == 30
    mixed = [*blocks, _row(MON, "t-m1", _at(MON, 40), 5)]
    assert _units(tmp_path, MON, mixed) == 40
    assert _units(tmp_path, TUE, [_row(TUE, "s-b1", _at(TUE, 15), None)]) == 60


def test_full_reward_and_penalty_unchanged(tmp_path: Path) -> None:
    others = {"workout": 0, "leetcode": 0, "reading": 0}
    full = resolve({**others, "tutor": _units(tmp_path, TUE, _minutes(TUE, 15))}, TUE)
    none = resolve({**others, "tutor": 0}, TUE)
    assert full.term("tutor").gaming_minutes == 60
    assert full.term("tutor").shutdown_minutes == 60
    assert full.base == none.base
    assert none.term("tutor").gaming_minutes == 0


@pytest.mark.parametrize("offset", range(7))
def test_raise_only_against_0_9_0(offset: int) -> None:
    day = TUTOR_QUOTA_FROM + timedelta(days=offset)
    for minutes in range(91):
        assert tutor_day_units(TUTOR, minutes, day) >= TUTOR.capped(minutes)
