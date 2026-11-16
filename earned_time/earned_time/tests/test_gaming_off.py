# Copyright (c) 2026 Krzysztof Rudnicki
"""The gaming stick is gone (0.22.0): one dated switch, shutdown stays."""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

import pytest

import earned_time
from earned_time import (
    GAMING_UNLIMITED_FROM,
    Earner,
    gaming_enforced,
    leisure_active,
    resolve,
    sick_shutdown_from,
)

if TYPE_CHECKING:
    from pathlib import Path

SWITCH = date(2026, 11, 16)
BEFORE = SWITCH - timedelta(days=1)
AFTER = SWITCH + timedelta(days=1)
ALL = {"workout": 1, "leetcode": 1, "reading": 1, "tutor": 60}
NONE = dict.fromkeys(ALL, 0)
ONE_MISSING = {**ALL, "reading": 0}


def test_the_switch_is_kuhys_date() -> None:
    assert date(2026, 11, 16) == GAMING_UNLIMITED_FROM


@pytest.mark.parametrize(
    ("day", "enforced"), [(BEFORE, True), (SWITCH, False), (AFTER, False)]
)
def test_gaming_enforced_around_the_switch(day: date, *, enforced: bool) -> None:
    assert gaming_enforced(day) is enforced


@pytest.mark.parametrize(
    ("day", "enforced"), [(BEFORE, True), (SWITCH, False), (AFTER, False)]
)
def test_resolution_reports_it(day: date, *, enforced: bool) -> None:
    assert resolve(ALL, day).gaming_enforced is enforced


def test_leisure_is_off_from_the_switch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "leisure_from"
    path.write_bytes(b"2026-11-09\n")
    monkeypatch.setattr("earned_time._leisure.LEISURE_FROM_PATH", path)
    assert leisure_active(BEFORE, path)
    assert not leisure_active(SWITCH, path)
    assert not leisure_active(AFTER, path)


def test_every_public_name_survives() -> None:
    for name in (
        "GAMING_BASE_MINUTES",
        "GAMING_CEILING_MINUTES",
        "LEISURE_FROM",
        "LEISURE_FROM_PATH",
        "gaming_base_minutes_for",
        "gaming_ceiling_minutes_for",
        "leisure_active",
        "leisure_from",
    ):
        assert hasattr(earned_time, name)


@pytest.mark.parametrize("day", [SWITCH, AFTER])
def test_all_done_is_23_00_and_one_missing_is_less(day: date) -> None:
    assert resolve(ALL, day).shutdown_minutes == 23 * 60
    missing = resolve(ONE_MISSING, day).shutdown_minutes
    assert missing == 22 * 60
    assert resolve(NONE, day).shutdown_minutes == 18 * 60


def test_sick_pay_is_the_rung_pay_after_the_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Gaming pay is made to differ from the rung, to see which one is used."""
    monkeypatch.setattr(Earner, "gaming_for", lambda _s, units: 500 if units else 0)
    answers = {**NONE, "leetcode": 1}
    before = resolve(answers, BEFORE, sick=True)
    after = resolve(answers, SWITCH, sick=True)
    assert before.shutdown_minutes == 23 * 60  # 20:00 + gaming 500, capped
    assert after.shutdown_minutes == sick_shutdown_from(60, SWITCH) == 21 * 60


@pytest.mark.parametrize("day", [BEFORE, SWITCH])
@pytest.mark.parametrize("answers", [NONE, {**NONE, "leetcode": 1}, ONE_MISSING, ALL])
def test_sick_numbers_are_equal_today(day: date, answers: dict[str, int]) -> None:
    """Rung pay equals gaming pay on the unified ladder: nothing moves."""
    sick = resolve(answers, day, sick=True)
    paid = sum(t.gaming_minutes for t in sick.terms)
    assert sick.shutdown_minutes == max(
        resolve(answers, day).shutdown_minutes,
        sick_shutdown_from(paid, day),
    )
