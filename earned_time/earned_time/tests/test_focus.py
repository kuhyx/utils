# Copyright (c) 2026 Krzysztof Rudnicki
"""The focus project earner: registry swap, pay, rounding, penalty, fail mode."""

from __future__ import annotations

from datetime import date, timedelta
import logging
import sys
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

import earned_time
from earned_time import (
    TUTOR_EARNERS,
    FocusEarner,
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
from earned_time._match import focus_match, focus_minutes
from earned_time.tests._maturity_rows import at, ledger_file, signed

if TYPE_CHECKING:
    from pathlib import Path

START = date(2026, 11, 2)
DAY = START + timedelta(days=1)


def project(**changes: object) -> SimpleNamespace:
    """A fake ``focus_project.Project`` (the contract's fields)."""
    fields: dict[str, object] = {
        "start": START,
        "end": START + timedelta(days=3),
        "replaces": ("leetcode", "reading", "tutor"),
        "daily_minutes": 120,
    }
    return SimpleNamespace(**{**fields, **changes})


def activate(monkeypatch: pytest.MonkeyPatch, active: object) -> None:
    """Make ``focus_project.active`` return ``active`` on project days only."""

    def on(day: date) -> object:
        return active if START <= day <= START + timedelta(days=3) else None

    monkeypatch.setitem(sys.modules, "focus_project", SimpleNamespace(active=on))


def row(
    minutes: object, n: int, day: date = DAY, **detail: object
) -> dict[str, object]:
    """A signed focus credit row ending at noon on ``day``."""
    return signed(
        {
            "kind": "credit",
            "entry_id": f"hr-{day:%Y%m%d}-m{n}",
            "day": day.isoformat(),
            "detail": {"minutes": minutes, "ended_at": at(day), **detail},
        }
    )


def focus(monkeypatch: pytest.MonkeyPatch, **changes: object) -> FocusEarner:
    """Today's focus earner under a fake project."""
    activate(monkeypatch, project(**changes))
    (found,) = (e for e in earners_for(DAY) if e.name == "focus")
    assert isinstance(found, FocusEarner)
    return found


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


def test_a_full_day_pays_what_the_replaced_gates_paid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = focus(monkeypatch)
    assert item.max_units == 120
    assert (item.gaming_for(120), item.shutdown_for(120, DAY)) == (180, 180)
    assert (item.gaming_for(999), item.shutdown_for(999, DAY)) == (180, 180)
    assert (item.max_gaming_minutes, item.gaming_for(-5)) == (180, 0)


def test_pay_is_floored_on_the_summed_minutes(monkeypatch: pytest.MonkeyPatch) -> None:
    item = focus(monkeypatch)
    assert [item.gaming_for(n) for n in (1, 2, 3, 7)] == [1, 3, 4, 10]
    assert [item.shutdown_for(n, DAY) for n in (1, 2, 3, 7)] == [1, 3, 4, 10]


def test_many_small_rows_pay_what_one_row_pays(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, key_file: Path
) -> None:
    item = focus(monkeypatch)
    many = ledger_file(tmp_path, [row(1, n) for n in range(1, 8)])
    one = tmp_path / "one.json"
    one.write_text(ledger_file(tmp_path, [row(7, 7)]).read_text(encoding="utf-8"))
    units = credit_units(item, many, key_file, DAY)
    assert units == credit_units(item, one, key_file, DAY) == 7
    assert item.gaming_for(units or 0) == 10


def test_resolve_prices_base_terms_and_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    activate(monkeypatch, project())
    nothing = resolve({"workout": 0, "focus": 0}, DAY, leisure=False)
    assert nothing.base.gaming_minutes == 300 - 120
    assert nothing.base.shutdown_minutes == 18 * 60
    half = resolve({"workout": 0, "focus": 60}, DAY, leisure=False)
    assert half.gaming_minutes == 180 + 90
    assert half.shutdown_minutes == 18 * 60 + 90
    full = resolve({"workout": 1, "focus": 120}, DAY, leisure=False)
    assert full.shutdown_minutes == 23 * 60


def test_a_project_day_is_neutral_against_the_gates_it_replaced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    activate(monkeypatch, project())
    zero = {"workout": 0, "leetcode": 0, "reading": 0, "tutor": 0, "focus": 0}
    done = {"workout": 1, "leetcode": 1, "reading": 1, "tutor": 60, "focus": 120}
    for answers in (zero, done):
        old = resolve(answers, DAY, TUTOR_EARNERS, leisure=False)
        new = resolve(answers, DAY, leisure=False)
        assert (new.gaming_minutes, new.shutdown_minutes) == (
            old.gaming_minutes,
            old.shutdown_minutes,
        )


def test_the_penalty_is_not_delayed_by_the_first_credit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = focus(monkeypatch)
    assert penalty_start(item, START) == penalty_start(item, None) == START
    answers = {"workout": 0, "focus": 0}
    plain = resolve(answers, START, leisure=False)
    paid = resolve(answers, START, first_credits={"focus": START}, leisure=False)
    assert paid.base == plain.base
    assert plain.base.gaming_minutes == 300 - 120


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
    assert (item.gaming_minutes, item.shutdown_minutes) == (60, 60)


@pytest.mark.parametrize("failure", [ImportError("gone"), ValueError("bad json")])
def test_a_broken_focus_project_means_no_project_and_logs_once(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    failure: Exception,
) -> None:
    def broken(_day: date) -> object:
        raise failure

    monkeypatch.setitem(sys.modules, "focus_project", SimpleNamespace(active=broken))
    monkeypatch.setattr("earned_time._focus._warned", set())
    with caplog.at_level(logging.WARNING):
        assert earners_for(DAY) is TUTOR_EARNERS
        assert earners_for(DAY) is TUTOR_EARNERS
    assert sum("behaving as if no project" in m for m in caplog.messages) == 1


def test_a_missing_package_is_no_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "focus_project", None)
    assert earners_for(DAY) is TUTOR_EARNERS


def test_rows_count_by_ended_at_then_by_day(caplog: pytest.LogCaptureFixture) -> None:
    window = earned_time.day_window(DAY)
    assert focus_match(row(5, 5), window)
    assert not focus_match(row(5, 5, START), window)
    nostamp = signed(
        {"kind": "credit", "day": DAY.isoformat(), "detail": {"minutes": 5}}
    )
    assert focus_match(nostamp, window)
    assert not focus_match({**nostamp, "day": START.isoformat()}, window)
    with caplog.at_level(logging.WARNING):
        assert not focus_match(row(0, 1), window)
    assert "bad minutes" in caplog.text


@pytest.mark.parametrize("bad", [0, -1, True, 1.5, "5", None])
def test_minutes_must_be_a_positive_int(bad: object) -> None:
    assert focus_minutes({"detail": {"minutes": bad}}) is None
    assert focus_minutes({"detail": "x"}) is None
    assert focus_minutes({"detail": {"minutes": 4}}) == 4
