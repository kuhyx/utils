# Copyright (c) 2026 Krzysztof Rudnicki
"""More 0.10.0 backing cases: sources, projects, the cutover midnight, chains.

The core rule lives in ``test_backing.py``; these pin the edges the spec
named (C5-C7) with leetcode-ledger and other-project fixtures.
"""

from __future__ import annotations

from datetime import date
import json
from typing import TYPE_CHECKING

import pytest

import focus_project as fp
from focus_project import minutes
from focus_project._paths import activity_path
from focus_project.tests.test_leetcode_source import ac_row, write
from focus_project.tests.test_minutes import at

if TYPE_CHECKING:
    from pathlib import Path

DAY = date(2026, 11, 9)  # after the cutover
PRE = date(2026, 11, 7)  # before it


@pytest.fixture(autouse=True)
def _home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Nothing may fall back to the real home directory."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


def make(pid: str = "hr", patterns: tuple[str, ...] = ("leetcode.com",)) -> None:
    fp.create_project(
        pid,
        name=pid,
        start=date(2026, 11, 6),
        end=date(2026, 11, 12),
        replaces=["leetcode"],
        daily_minutes=240,
        unlock_minutes=30,
        site_patterns=list(patterns),
    )


def rows(*items: tuple[str, str, float] | tuple[str, str, float, str]) -> None:
    """Append ``(source, kind, ts[, project])`` events (project default hr)."""
    activity_path().parent.mkdir(parents=True, exist_ok=True)
    with activity_path().open("a", encoding="utf-8") as handle:
        for item in items:
            source, kind, ts = item[:3]
            pid = item[3] if len(item) == 4 else "hr"
            row = {"ts": ts, "source": source, "kind": kind, "project": pid}
            handle.write(json.dumps(row) + "\n")


def timer(day: date, *marks: tuple[int, int]) -> None:
    """A segment: start at the first mark, check-ins, stop at the last."""
    kinds = ["start", *["checkin"] * (len(marks) - 2), "stop"]
    rows(
        *(
            ("timer", k, at(h, m, day=day))
            for k, (h, m) in zip(kinds, marks, strict=True)
        )
    )


def beat(source: str, h: int, m: int, day: date = DAY, pid: str = "hr") -> None:
    rows((source, "heartbeat", at(h, m, day=day), pid))


@pytest.mark.parametrize("source", ["sql_drills", "leetcode"])
def test_sql_drills_and_leetcode_heartbeats_back_too(source: str) -> None:
    make()
    timer(DAY, (9, 0), (9, 5), (9, 10))
    beat(source, 9, 5)
    assert minutes.minutes_for(DAY) == 10


def test_browser_and_other_project_beats_do_not_back() -> None:
    make()  # "other" needs no registry entry: rows are filtered by id
    timer(DAY, (9, 0), (9, 5), (9, 10))
    beat("browser", 9, 4)
    beat("tutor", 9, 4, pid="other")
    assert minutes.minutes_for(DAY) == 5  # the browser beat's own window only
    assert minutes.unbacked_minutes_for(DAY) == 6  # 9:04-9:10


def test_accepted_submission_backs_a_leetcode_project(tmp_path: Path) -> None:
    make()
    timer(DAY, (9, 0), (9, 5), (9, 10))
    write(tmp_path, ac_row(at(9, 4, day=DAY)))
    assert minutes.minutes_for(DAY) == 11  # 8:59-9:10


def test_submission_does_not_back_a_non_leetcode_project(tmp_path: Path) -> None:
    make("hr", ("sqlzoo.net",))
    timer(DAY, (9, 0), (9, 5), (9, 10))
    write(tmp_path, ac_row(at(9, 4, day=DAY)))
    assert minutes.minutes_for(DAY) == 0


def test_span_across_the_cutover_midnight_follows_the_day() -> None:
    make()
    rows(
        ("timer", "start", at(23, 58, day=date(2026, 11, 7))),
        ("timer", "checkin", at(0, 3, day=date(2026, 11, 8))),
        ("timer", "stop", at(0, 5, day=date(2026, 11, 8))),
    )
    assert minutes.minutes_for(date(2026, 11, 7)) == 2
    assert minutes.minutes_for(date(2026, 11, 8)) == 0
    assert minutes.unbacked_minutes_for(date(2026, 11, 8)) == 5


def test_tutor_chained_span_is_backed_but_earlier_reading_is_not() -> None:
    """A tutor beat chains the segment (0.8.0) and backs the span it ends.

    start 9:00, checkin 9:08, tutor beat 9:16: the span 9:08-9:16 ends at a
    backing beat and earns; 9:00-9:08 has no beat in or 5 min before it and
    nothing bridges it, so it shows as unbacked.
    """
    make()
    rows(
        ("timer", "start", at(9, 0, day=DAY)),
        ("timer", "checkin", at(9, 8, day=DAY)),
    )
    beat("tutor", 9, 16)
    assert minutes.minutes_for(DAY) == 8
    assert minutes.unbacked_minutes_for(DAY) == 8
