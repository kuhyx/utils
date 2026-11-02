# Copyright (c) 2026 Krzysztof Rudnicki
"""Overtime carries over: own minutes, the bank, pay and the carry ledger rows."""

from __future__ import annotations

from datetime import date, timedelta
import json
from pathlib import Path  # noqa: TC003
from typing import Any

import earned_time
import pytest

import focus_project as fp
from focus_project import carry, harvest, ledger, minutes
from focus_project.tests.test_minutes import D1, at, events, project

KEY = b"k" * 32
D2 = D1 + timedelta(days=1)
D3 = D2 + timedelta(days=1)
D4 = D3 + timedelta(days=1)  # the last day of project()
D5 = D4 + timedelta(days=1)  # after the end


@pytest.fixture(autouse=True)
def _key(tmp_path: Path) -> None:
    (tmp_path / "hmac.key").write_bytes(KEY)


def work(day: date, mins: int) -> None:
    """``mins`` focused minutes on ``day``: tutor heartbeats every five minutes."""
    events(
        *(
            ("tutor", "heartbeat", at(8, 0, day=day) + 300 * k)
            for k in range(1, mins // 5 + 1)
        )
    )


def rows() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = json.loads(ledger.ledger_path().read_text())["entries"]
    return out


def test_own_minutes_are_not_capped_but_pay_is() -> None:
    project()
    work(D1, 125)
    assert carry.own_minutes(D1) == 125
    assert minutes.minutes_for(D1) == 120


def test_overtime_banks_into_the_next_day() -> None:
    project()
    work(D1, 125)
    assert carry.balance(D1) == carry.Balance(own=125, carried_in=0, carry_out=5)
    assert carry.balance(D2) == carry.Balance(own=0, carried_in=5, carry_out=0)
    assert minutes.minutes_for(D2) == 5


def test_carry_adds_to_own_minutes_on_the_next_day() -> None:
    project()
    work(D1, 125)
    work(D2, 100)
    assert minutes.minutes_for(D2) == 105
    assert carry.balance(D2).carry_out == 0


def test_the_bank_is_capped_at_sixty() -> None:
    project()
    work(D1, 200)
    assert carry.balance(D1).carry_out == carry.BANK_CAP == 60


def test_overtime_chains_over_days() -> None:
    project()
    work(D1, 130)
    work(D2, 125)
    assert carry.balance(D2) == carry.Balance(own=125, carried_in=10, carry_out=15)
    assert minutes.minutes_for(D3) == 15


def test_the_bank_never_crosses_the_project_end() -> None:
    project()
    work(D4, 150)
    assert carry.balance(D4).carry_out == 30
    assert minutes.minutes_for(D5) == 0
    assert carry.balance(D5) == carry.Balance(0, 0, 0)


def test_the_first_day_has_nothing_banked_in() -> None:
    project()
    assert carry.balance(D1 - timedelta(days=1)).carried_in == 0
    assert carry.balance(D1).carried_in == 0


def test_a_past_target_is_used_for_a_past_day() -> None:
    project()
    work(D1, 125)
    fp.update_project("hr", today=D2, daily_minutes=100, unlock_minutes=30)
    assert carry.balance(D1).carry_out == 5  # D1 still judged at 120
    assert carry.balance(D2).carried_in == 5


def test_status_reports_real_minutes_and_the_bank() -> None:
    project()
    work(D1, 125)
    shown = fp.status(D1)
    assert shown["minutes"] == 125
    assert shown["own_minutes"] == 125
    assert shown["counted_minutes"] == 120
    assert (shown["carried_in"], shown["carry_out"]) == (0, 5)
    nxt = fp.status(D2)
    assert (nxt["minutes"], nxt["carried_in"]) == (5, 5)


def test_status_without_a_project_has_zero_bank() -> None:
    shown = fp.status(D1)
    assert (shown["own_minutes"], shown["carried_in"], shown["carry_out"]) == (0, 0, 0)


def test_unreadable_registry_banks_nothing(data: Path) -> None:
    data.mkdir(parents=True)
    (data / "projects.json").write_text("{")
    assert carry.balance(D2) == carry.Balance(0, 0, 0)
    assert carry.own_minutes(D2) == 0


def test_harvest_pays_own_rows_then_one_carry_row() -> None:
    project()
    work(D1, 125)
    work(D2, 100)
    harvest.harvest(now=at(23, 0, day=D2))
    got = {r["entry_id"]: r for r in rows()}
    assert got["hr-20261102-m120"]["detail"]["minutes"] == 120
    assert got["hr-20261103-carry"]["detail"]["minutes"] == 5
    assert got["hr-20261103-carry"]["detail"]["carry"] is True
    assert got["hr-20261103-m100"]["detail"]["minutes"] == 100
    assert all(earned_time.verified(r, KEY) for r in got.values())
    assert ledger.paid_minutes(rows(), KEY, "hr", D2) == 105


def test_pay_never_exceeds_the_daily_target() -> None:
    project()
    work(D1, 125)
    work(D2, 130)
    harvest.harvest(now=at(23, 0, day=D2))
    assert ledger.paid_minutes(rows(), KEY, "hr", D2) == 120
    assert minutes.minutes_for(D2) == 120


def test_carry_is_paid_at_the_start_of_the_day_and_not_again() -> None:
    project()
    work(D1, 125)
    harvest.harvest(now=at(0, 5, day=D2))
    before = rows()
    assert [r["entry_id"] for r in before if r["day"] == "2026-11-03"] == [
        "hr-20261103-carry"
    ]
    harvest.harvest(now=at(0, 6, day=D2))
    assert rows() == before


def test_late_data_for_yesterday_pays_only_the_carry_delta() -> None:
    project()
    work(D1, 125)
    harvest.harvest(now=at(9, 0, day=D2))
    work(D1, 130)  # a late phone sync: five more minutes
    harvest.harvest(now=at(9, 5, day=D2))
    paid = [r for r in rows() if r["detail"].get("carry")]
    assert [r["entry_id"] for r in paid] == [
        "hr-20261103-carry",
        "hr-20261103-carry-m10",
    ]
    assert ledger.paid_minutes(rows(), KEY, "hr", D2) == 10


def test_own_rows_leave_room_for_the_carry() -> None:
    project()
    work(D1, 125)
    work(D2, 120)
    harvest.harvest(now=at(23, 0, day=D2))
    assert ledger.paid_minutes(rows(), KEY, "hr", D2) == 120
    assert "hr-20261103-m115" in {r["entry_id"] for r in rows()}
