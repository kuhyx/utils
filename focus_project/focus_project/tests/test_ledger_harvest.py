# Copyright (c) 2026 Krzysztof Rudnicki
"""Signed rows, idempotency, harvester paths."""

from __future__ import annotations

from datetime import date, timedelta
import json
import logging
from pathlib import Path  # noqa: TC003
from typing import Any

import earned_time
import pytest

import focus_project as fp
from focus_project import harvest, ledger, minutes
from focus_project.tests.test_minutes import D1, at, events, project

KEY = b"k" * 32


@pytest.fixture(autouse=True)
def _key(tmp_path: Path) -> None:
    (tmp_path / "hmac.key").write_bytes(KEY)


def rows() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = json.loads(ledger.ledger_path().read_text())[
        "entries"
    ]
    return entries


def beats(*times: float) -> None:
    events(*(("tutor", "heartbeat", t) for t in times))


def test_credit_writes_signed_row_with_contract_fields() -> None:
    project()
    beats(at(9, 30))
    assert harvest.harvest(now=at(9, 31)) == 0
    (row,) = rows()
    assert row["entry_id"] == "hr-20261102-m5"
    assert row["day"] == "2026-11-02"
    assert row["detail"]["minutes"] == 5
    assert row["detail"]["project"] == "hr"
    assert row["detail"]["ended_at"] == at(9, 31)
    assert earned_time.verified(row, KEY)


def test_second_run_is_idempotent() -> None:
    project()
    beats(at(9, 30))
    harvest.harvest(now=at(9, 31))
    harvest.harvest(now=at(9, 32))
    assert len(rows()) == 1


def test_growth_writes_increment_rows_that_sum_to_total() -> None:
    project()
    beats(at(9, 30))
    harvest.harvest(now=at(9, 31))
    beats(at(9, 38))  # union: 9:25..9:30 + 9:33..9:38 = 10
    harvest.harvest(now=at(9, 39))
    got = rows()
    assert [r["entry_id"] for r in got] == ["hr-20261102-m5", "hr-20261102-m10"]
    assert [r["detail"]["minutes"] for r in got] == [5, 5]
    assert ledger.paid_minutes(got, KEY, "hr", D1) == minutes.minutes_for(D1) == 10


def test_yesterday_is_harvested_after_midnight() -> None:
    project()
    beats(at(23, 58))
    harvest.harvest(now=at(0, 1, day=D1 + timedelta(days=1)))
    (row,) = rows()
    assert row["day"] == "2026-11-02"
    assert row["detail"]["ended_at"] < at(0, 0, day=D1 + timedelta(days=1))


def test_no_project_writes_nothing() -> None:
    beats(at(9, 30))
    assert harvest.harvest(now=at(9, 31)) == 0
    assert not ledger.ledger_path().exists()


def test_unreadable_key_fails_loudly_and_writes_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "hmac.key").unlink()
    project()
    beats(at(9, 30))
    with caplog.at_level(logging.ERROR):
        assert harvest.harvest(now=at(9, 31)) == 1
    assert "unreadable" in caplog.text
    assert not ledger.ledger_path().exists()


def test_corrupt_ledger_is_not_emptied() -> None:
    project()
    beats(at(9, 30))
    ledger.ledger_path().parent.mkdir(parents=True, exist_ok=True)
    ledger.ledger_path().write_text("{oops")
    assert harvest.harvest(now=at(9, 31)) == 1
    assert ledger.ledger_path().read_text() == "{oops"


def test_ledger_without_entries_array_is_an_error() -> None:
    ledger.ledger_path().parent.mkdir(parents=True, exist_ok=True)
    ledger.ledger_path().write_text('{"entries": 3}')
    with pytest.raises(ledger.LedgerError):
        ledger.read_rows(ledger.ledger_path())


def test_broken_registry_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_day: date) -> None:
        msg = "corrupt"
        raise fp.RegistryError(msg)

    monkeypatch.setattr("focus_project._api.list_projects", boom)
    assert harvest.harvest(now=at(9, 31)) == 1


def test_a_day_that_fails_does_not_stop_the_others(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project()
    beats(at(9, 30))
    real = harvest.harvest_day

    def flaky(day: date, now: float) -> int:
        if day == D1:
            msg = "disk"
            raise OSError(msg)
        return real(day, now)

    monkeypatch.setattr(harvest, "harvest_day", flaky)
    assert harvest.harvest(now=at(9, 31, day=D1 + timedelta(days=1))) == 1


def test_empty_key_file_counts_as_unreadable(tmp_path: Path) -> None:
    (tmp_path / "hmac.key").write_bytes(b"\n")
    assert ledger.read_key() is None


def test_forged_and_malformed_rows_do_not_count() -> None:
    good = ledger.build_row("hr", D1, 5, 5, KEY, now=at(9))
    forged = {
        **good,
        "entry_id": "hr-20261102-m50",
        "detail": {**good["detail"], "minutes": 50},
    }
    other_key = ledger.build_row("hr", D1, 9, 9, b"x" * 32, now=at(9))
    junk: list[Any] = [
        "str",
        {"kind": "charge"},
        {**good, "detail": "no"},
        {**good, "day": "2026-11-03"},
        {**good, "detail": {**good["detail"], "project": "other"}},
        {**good, "detail": {**good["detail"], "minutes": True}},
        {**good, "detail": {**good["detail"], "minutes": 0}},
        forged,
        other_key,
    ]
    assert ledger.paid_minutes([good, *junk], KEY, "hr", D1) == 5


def test_repeated_entry_id_pays_once_at_smallest() -> None:
    a = ledger.build_row("hr", D1, 10, 10, KEY, now=at(9))
    b = ledger.build_row("hr", D1, 10, 4, KEY, now=at(9))
    assert ledger.paid_minutes([a, b], KEY, "hr", D1) == 4


def test_unverified_same_id_row_blocks_write() -> None:
    p = project_obj()
    row = ledger.build_row("hr", D1, 5, 5, KEY, now=at(9))
    row["hmac"] = "bad"
    ledger.ledger_path().parent.mkdir(parents=True, exist_ok=True)
    ledger.ledger_path().write_text(json.dumps({"entries": [row]}))
    with pytest.raises(ledger.LedgerError, match="unverified"):
        ledger.credit_to(p, D1, 5, now=at(9))


def test_readback_failure_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    p = project_obj()
    real = ledger._write_rows
    monkeypatch.setattr(ledger, "_write_rows", lambda path, _rows: real(path, []))
    with pytest.raises(ledger.LedgerError, match="read-back"):
        ledger.credit_to(p, D1, 5, now=at(9))


def project_obj() -> fp.Project:
    project()
    found = fp.active(D1)
    assert found is not None
    return found


def test_main_exits_with_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(harvest, "harvest", lambda: 7)
    with pytest.raises(SystemExit) as info:
        harvest.main()
    assert info.value.code == 7


def test_harvest_day_without_a_project_pays_nothing() -> None:
    beats(at(9, 30))
    assert harvest.harvest_day(D1, at(9, 31)) == 0
    assert not ledger.ledger_path().exists()
