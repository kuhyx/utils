# Copyright (c) 2026 Krzysztof Rudnicki
"""The focus project earner: registry swap, pay, rounding, penalty."""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

import pytest

import earned_time
from earned_time import (
    TUTOR_EARNERS,
    all_earners,
    credit_units,
    earners_for,
    extra_shutdown_minutes_for,
    maturity,
    penalty_start,
    resolve,
    shutdown_minutes_for,
)
from earned_time._focus import focus_earner
from earned_time.tests._focus_fakes import DAY, START, activate, focus, project, row
from earned_time.tests._maturity_rows import ledger_file, signed

if TYPE_CHECKING:
    from pathlib import Path


def test_the_replaced_gates_leave_and_focus_joins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    activate(monkeypatch, project())
    assert [e.name for e in earners_for(DAY)] == ["workout", "focus"]
    assert earners_for(START - timedelta(days=1)) is TUTOR_EARNERS
    assert earners_for(START + timedelta(days=4)) is TUTOR_EARNERS


def test_book_is_a_synonym_and_unreplaced_gates_stay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    activate(monkeypatch, project(replaces=("book",)))
    assert [e.name for e in earners_for(DAY)] == [
        "workout",
        "leetcode",
        "tutor",
        "focus",
    ]
    item = earners_for(DAY)[-1]
    assert (item.gaming_minutes, item.shutdown_minutes) == (60, 60)


@pytest.mark.parametrize(
    "changes", [{"replaces": ("anki",)}, {"replaces": ()}, {"daily_minutes": 0}]
)
def test_a_project_that_changes_nothing_leaves_the_registry(
    monkeypatch: pytest.MonkeyPatch, changes: dict[str, object]
) -> None:
    activate(monkeypatch, project(**changes))
    assert earners_for(DAY) is TUTOR_EARNERS


def test_a_full_day_pays_the_cut_plus_the_free_leetcode_hour(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """kuhy 2026-11-02 (0.21.0): 2 gaming minutes per focus minute, 240 a day."""
    item = focus(monkeypatch)
    assert item.max_units == 120
    assert (item.gaming_for(120), item.shutdown_for(120, DAY)) == (240, 180)
    assert (item.gaming_for(999), item.shutdown_for(999, DAY)) == (240, 180)
    assert (item.max_gaming_minutes, item.gaming_for(-5)) == (240, 0)
    assert item.cut_gaming_minutes == 180


def test_pay_is_floored_on_the_summed_minutes(monkeypatch: pytest.MonkeyPatch) -> None:
    item = focus(monkeypatch)
    assert [item.gaming_for(n) for n in (1, 2, 3, 7)] == [2, 4, 6, 14]
    assert [item.shutdown_for(n, DAY) for n in (1, 2, 3, 7)] == [1, 3, 4, 10]
    odd = focus(monkeypatch, daily_minutes=90)
    assert [odd.gaming_for(n) for n in (1, 2, 90)] == [2, 5, 240]


def test_many_small_rows_pay_what_one_row_pays(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, key_file: Path
) -> None:
    item = focus(monkeypatch)
    many = ledger_file(tmp_path, [row(1, n) for n in range(1, 8)])
    one = tmp_path / "one.json"
    one.write_text(ledger_file(tmp_path, [row(7, 7)]).read_text(encoding="utf-8"))
    units = credit_units(item, many, key_file, DAY)
    assert units == credit_units(item, one, key_file, DAY) == 7
    assert item.gaming_for(units or 0) == 14


def test_carry_rows_pay_like_own_rows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, key_file: Path
) -> None:
    """focus_project 0.6.0 banks overtime as ``<project>-<YYYYMMDD>-carry`` rows."""
    item = focus(monkeypatch)
    carry = row(30, 0, carry=True)
    carry["entry_id"] = f"hr-{DAY:%Y%m%d}-carry"
    top_up = row(5, 0, carry=True)
    top_up["entry_id"] = f"hr-{DAY:%Y%m%d}-carry-m35"
    rows = [signed(carry), signed(top_up), row(85, 85)]
    ledger = ledger_file(tmp_path, rows)
    assert credit_units(item, ledger, key_file, DAY) == 120


def test_resolve_prices_base_terms_and_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    activate(monkeypatch, project())
    nothing = resolve({"workout": 0, "focus": 0}, DAY, leisure=False)
    assert nothing.base.gaming_minutes == 300 - 180
    assert nothing.base.shutdown_minutes == 18 * 60
    half = resolve({"workout": 0, "focus": 60}, DAY, leisure=False)
    assert half.gaming_minutes == 120 + 120
    assert half.shutdown_minutes == 18 * 60 + 90
    full = resolve({"workout": 1, "focus": 120}, DAY, leisure=False)
    assert full.shutdown_minutes == 23 * 60
    assert full.gaming_minutes == 300 - 180 + 240 + 120 == 8 * 60


def test_a_full_project_day_pays_what_the_replaced_gates_paid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A full project day equals the old full day, LeetCode's free hour too."""
    activate(monkeypatch, project())
    done = {"workout": 1, "leetcode": 1, "reading": 1, "tutor": 60, "focus": 120}
    old = resolve(done, DAY, TUTOR_EARNERS, leisure=False)
    new = resolve(done, DAY, leisure=False)
    assert new.shutdown_minutes == old.shutdown_minutes
    # kuhy 2026-11-02 (0.21.0): the day cuts 180 but pays 240, so a full day
    # is the old full day (8 h); only an idle day is worse.
    assert new.gaming_minutes == old.gaming_minutes == 8 * 60


def test_an_idle_project_day_also_cuts_the_free_leetcode_hour(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """kuhy 2026-11-02: a project day cuts all it can pay (180), not 120."""
    activate(monkeypatch, project())
    zero = {"workout": 0, "leetcode": 0, "reading": 0, "tutor": 0, "focus": 0}
    old = resolve(zero, DAY, TUTOR_EARNERS, leisure=False)
    new = resolve(zero, DAY, leisure=False)
    assert new.gaming_minutes == old.gaming_minutes - 60
    assert new.shutdown_minutes == old.shutdown_minutes


def test_the_penalty_is_not_delayed_by_the_first_credit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = focus(monkeypatch)
    assert penalty_start(item, START) == penalty_start(item, None) == START
    answers = {"workout": 0, "focus": 0}
    plain = resolve(answers, START, leisure=False)
    paid = resolve(answers, START, first_credits={"focus": START}, leisure=False)
    assert paid.base == plain.base
    assert plain.base.gaming_minutes == 300 - 180


def test_maturity_reads_the_focus_ledger(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, key_file: Path
) -> None:
    item = focus(monkeypatch)
    ledger = ledger_file(tmp_path, [row(30, 30, START), row(30, 60, START)])
    found = maturity(item, ledger, key_file, DAY)
    assert (found.first_credit, found.penalty_start) == (START, START)


def test_the_first_and_second_minute_follow_the_floor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = focus(monkeypatch)
    assert shutdown_minutes_for(item, DAY) == 1
    assert extra_shutdown_minutes_for(item, DAY) == 2
    assert shutdown_minutes_for(earned_time.ANKI, date(2026, 10, 9)) == 30
    assert extra_shutdown_minutes_for(earned_time.ANKI, date(2026, 10, 9)) == 0


def test_the_path_unit_watches_the_focus_ledger() -> None:
    assert earned_time.FOCUS_LEDGER in {e.ledger for e in all_earners()}


def test_focus_pays_only_replaced_gates_that_exist() -> None:
    item = focus_earner(project(), (earned_time.LEETCODE,), DAY)
    assert (item.gaming_minutes, item.shutdown_minutes) == (120, 60)
    assert item.cut_gaming_minutes == 60
