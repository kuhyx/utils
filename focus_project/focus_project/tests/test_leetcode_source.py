# Copyright (c) 2026 Krzysztof Rudnicki
"""The accepted-submission adapter, incl. read-only replay of the real ledger."""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
from typing import Any

import earned_time
import pytest

import focus_project as fp
from focus_project import minutes, sources
from focus_project.sources import leetcode
from focus_project.tests.test_backing import DAY, proj, rows
from focus_project.tests.test_backing import at as day_at
from focus_project.tests.test_minutes import D1, at, project

KEY = b"k" * 32


def ac_row(ts: float, eid: str = "ac:1", key: bytes = KEY) -> dict[str, Any]:
    row: dict[str, Any] = {
        "entry_id": eid,
        "kind": "credit",
        "day": "2026-11-02",
        "amount": 1,
        "detail": {"title_slug": "x", "submitted_at": str(int(ts))},
    }
    row["hmac"] = earned_time.entry_signature(row, key)
    return row


def write(tmp_path: Path, *rows: object) -> None:
    (tmp_path / "hmac.key").write_bytes(KEY)
    (tmp_path / "lc.json").write_text(json.dumps({"version": 1, "entries": list(rows)}))


def test_submission_is_a_five_minute_heartbeat(tmp_path: Path) -> None:
    project()
    write(tmp_path, ac_row(at(10)), ac_row(at(10, 2), "ac:2"))
    assert minutes.minutes_for(D1) == 7  # union 9:55..10:02


def test_other_rows_and_forgeries_ignored(tmp_path: Path) -> None:
    project()
    charge = {**ac_row(at(10), "charge:2026-11-02"), "kind": "charge"}
    bad_detail = ac_row(at(10), "ac:3")
    bad_detail["detail"] = {"submitted_at": "soon"}
    bad_detail["hmac"] = earned_time.entry_signature(bad_detail, KEY)
    no_detail = ac_row(at(10), "ac:4")
    no_detail["detail"] = None
    no_detail["hmac"] = earned_time.entry_signature(no_detail, KEY)
    write(
        tmp_path,
        charge,
        ac_row(at(10), "ac:5", key=b"x" * 32),
        bad_detail,
        no_detail,
        "junk",
    )
    assert minutes.minutes_for(D1) == 0


def test_project_without_leetcode_pattern_ignores_ledger(tmp_path: Path) -> None:
    fp.create_project(
        "sql",
        name="SQL",
        start=D1,
        end=D1,
        replaces=["reading"],
        daily_minutes=60,
        unlock_minutes=10,
        site_patterns=["sqlzoo.net"],
    )
    write(tmp_path, ac_row(at(10)))
    assert minutes.minutes_for(D1) == 0


def test_no_key_contributes_zero(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    project()
    write(tmp_path, ac_row(at(10)))
    (tmp_path / "hmac.key").unlink()
    assert minutes.minutes_for(D1) == 0
    assert "no signing key" in caplog.text


def test_missing_or_corrupt_ledger_contributes_zero(tmp_path: Path) -> None:
    project()
    (tmp_path / "hmac.key").write_bytes(KEY)
    assert minutes.minutes_for(D1) == 0
    (tmp_path / "lc.json").write_text("{")
    assert minutes.minutes_for(D1) == 0  # LedgerError caught by collect


def test_default_ledger_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv(leetcode.LEDGER_ENV)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert (
        leetcode.ledger_file() == tmp_path / ".local/share/leetcode_guard/ledger.json"
    )


REAL = Path.home() / ".local/share/leetcode_guard/ledger.json"
REAL_KEY = Path("/etc/workout-locker/hmac.key")


@pytest.mark.skipif(not (REAL.exists() and REAL_KEY.exists()), reason="no live ledger")
def test_read_only_replay_of_real_ledger(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every real accepted submission yields a heartbeat; nothing is written."""
    before = REAL.stat().st_mtime_ns
    monkeypatch.setenv(leetcode.LEDGER_ENV, str(REAL))
    monkeypatch.setenv("FOCUS_PROJECT_KEY", str(REAL_KEY))
    proj = fp.Project(
        id="x",
        name="x",
        start=date(2026, 1, 1),
        end=date(2026, 12, 31),
        replaces=("leetcode",),
        daily_minutes=120,
        unlock_minutes=30,
        site_patterns=("leetcode.com",),
    )
    got = leetcode.intervals(D1, proj)
    assert got
    assert all(b - a == sources.HEARTBEAT_WINDOW_S for a, b in got)
    assert REAL.stat().st_mtime_ns == before


def test_accepted_submission_backs_a_timer_span(tmp_path: Path) -> None:
    """0.10.0: an accepted submission backs timer time on a backed day."""
    proj()
    rows(("timer", "start", day_at(9)), ("timer", "stop", day_at(9, 10)))
    assert minutes.unbacked_minutes_for(DAY) == 10
    write(tmp_path, ac_row(day_at(9, 10)))
    assert minutes.unbacked_minutes_for(DAY) == 0
    assert minutes.minutes_for(DAY) == 10


def test_unreadable_ledger_leaves_heartbeat_backing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(_project: object) -> list[float]:
        raise OSError

    monkeypatch.setattr(leetcode, "submission_times", boom)
    proj()
    rows(
        ("timer", "start", day_at(9)),
        ("timer", "stop", day_at(9, 10)),
        ("tutor", "heartbeat", day_at(9, 10)),
    )
    assert minutes.unbacked_minutes_for(DAY) == 0
