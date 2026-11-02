# Copyright (c) 2026 Krzysztof Rudnicki
"""Harvester backfill: late-synced events for older project days are paid."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path  # noqa: TC003

import pytest

import focus_project as fp
from focus_project import harvest, ledger
from focus_project.tests.test_ledger_harvest import KEY, rows
from focus_project.tests.test_minutes import D1, at, events


@pytest.fixture(autouse=True)
def _key(tmp_path: Path) -> None:
    (tmp_path / "hmac.key").write_bytes(KEY)


def _late_phone_batch(start: date) -> None:
    """A phone offline since ``start`` delivers a full timer run late."""
    fp.create_project(
        "hr",
        name="HR",
        start=start,
        end=start + timedelta(days=5),
        replaces=["leetcode"],
        daily_minutes=120,
        unlock_minutes=30,
    )
    t = at(10, day=start)
    events(
        ("timer", "start", t),
        *(("timer", "checkin", t + i * 420) for i in range(1, 18)),
        ("timer", "stop", t + 17 * 420 + 60),
    )


def test_late_events_for_an_older_project_day_are_paid() -> None:
    """Friday's work, synced Monday, used to be skipped with exit 0."""
    fri = date(2026, 10, 30)
    _late_phone_batch(fri)
    assert harvest.harvest(now=at(10, day=D1)) == 0
    (row,) = rows()
    assert row["day"] == "2026-10-30"
    assert row["detail"]["minutes"] == 120
    assert row["detail"]["ended_at"] < at(0, day=fri + timedelta(days=1))
    assert harvest.harvest(now=at(10, 1, day=D1)) == 0  # idempotent
    assert len(rows()) == 1


def test_backfill_covers_a_finished_project_and_stops_at_its_last_day() -> None:
    first = date(2026, 10, 20)  # ran 20..25 Oct, long over
    _late_phone_batch(first)
    harvest.harvest(now=at(10, day=D1))
    assert [r["day"] for r in rows()] == ["2026-10-20"]


def test_backfill_is_bounded() -> None:
    old = D1 - timedelta(days=harvest.BACKFILL_DAYS + 5)
    _late_phone_batch(old)
    harvest.harvest(now=at(10, day=D1))
    assert not ledger.ledger_path().exists()  # beyond BACKFILL_DAYS
