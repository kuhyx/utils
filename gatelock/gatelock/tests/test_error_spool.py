# Copyright (c) 2026 Krzysztof Rudnicki
"""The error reporter's spool writer: entries, dedup, rate caps, waits."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from gatelock import _error_spool
from gatelock._error_spool import Reporter
from gatelock.tests.errorkit import Clock, raised, spool_lines

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def reporter(tmp_path: Path, clock: Clock) -> Reporter:
    return Reporter(
        app="leetcode-guard",
        repo="kuhyx/leetcode-guard",
        spool=tmp_path,
        build=5,
        version="0.3.0",
        clock=clock,
    )


def test_report_writes_one_entry(reporter: Reporter, tmp_path: Path) -> None:
    exc = raised()
    reporter.report("uncaught.python", exc, exc.__traceback__)
    (entry,) = spool_lines(tmp_path)
    assert entry["kind"] == "uncaught.python"
    assert entry["error"] == "ValueError: bad 12"
    assert entry["repo"] == "kuhyx/leetcode-guard"
    assert entry["mark"] == "leetcode_guard/"
    assert entry["build"] == 5
    assert entry["version"] == "0.3.0"
    assert entry["at"] == "2027-01-15T08:00:00.000Z"
    stack = entry["stack"]
    assert isinstance(stack, list)
    assert stack[0].startswith("__init__.py:")
    assert " in _boom" in stack[0]


def test_identical_errors_within_window_are_dropped(
    reporter: Reporter, tmp_path: Path, clock: Clock
) -> None:
    for _ in range(5):
        reporter.report("k", "same")
    assert len(spool_lines(tmp_path)) == 1
    clock.t += Reporter.WINDOW + 1
    reporter.report("k", "same")
    assert len(spool_lines(tmp_path)) == 2


def test_rate_cap_per_minute(reporter: Reporter, tmp_path: Path, clock: Clock) -> None:
    for i in range(Reporter.MAX_PER_MINUTE + 5):
        reporter.report("k", f"e{i}")
    assert len(spool_lines(tmp_path)) == Reporter.MAX_PER_MINUTE
    clock.t += 61
    reporter.report("k", "later")
    assert len(spool_lines(tmp_path)) == Reporter.MAX_PER_MINUTE + 1


def test_report_never_raises(reporter: Reporter, tmp_path: Path) -> None:
    class Bad:
        def __str__(self) -> str:
            raise RuntimeError

    reporter.report("k", Bad())
    (tmp_path / "leetcode-guard.jsonl").mkdir()  # an unwritable spool file
    reporter.report("k", "other")
    assert True


def test_report_inside_report_is_ignored(reporter: Reporter, tmp_path: Path) -> None:
    reporter._guard.busy = True
    reporter.report("k", "x")
    assert spool_lines(tmp_path) == []


def test_slow_wait_over_threshold_is_written(
    reporter: Reporter, tmp_path: Path, clock: Clock
) -> None:
    wait = reporter.begin("coach.load", route="coach")
    clock.t += 2.0
    wait.end()
    wait.end()  # repeat ends do nothing
    (entry,) = spool_lines(tmp_path)
    assert entry["kind"] == "perf.slow"
    assert entry["operation"] == "coach.load"
    assert entry["durationMs"] == 2000
    assert entry["route"] == "coach"
    assert entry["still"] is False
    assert entry["error"] == "coach.load waited 2000 ms"


def test_fast_wait_writes_nothing(
    reporter: Reporter, tmp_path: Path, clock: Clock
) -> None:
    with reporter.wait("quick"):
        clock.t += 0.5
    assert spool_lines(tmp_path) == []


def test_still_waiting_is_written_then_the_end(
    reporter: Reporter, tmp_path: Path, clock: Clock
) -> None:
    wait = reporter.begin("hung")
    clock.t += 6
    wait._still()
    clock.t += 1
    wait.end()
    still, end = spool_lines(tmp_path)
    assert still["still"] is True
    assert end["still"] is False
    assert still["waitId"] == end["waitId"]


def test_slow_rate_cap(reporter: Reporter, tmp_path: Path, clock: Clock) -> None:
    for _ in range(Reporter.MAX_SLOW_PER_MINUTE + 3):
        w = reporter.begin("op")
        clock.t += 1.5
        w.end()
    assert len(spool_lines(tmp_path)) == Reporter.MAX_SLOW_PER_MINUTE


def test_default_spool_and_mark(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    rep = Reporter(app="diet-guard", repo="kuhyx/diet-guard")
    assert rep.spool == tmp_path / "app-errors-spool"
    assert rep.mark == "diet_guard/"
    monkeypatch.delenv("XDG_STATE_HOME")
    assert Reporter(app="a", repo="kuhyx/a").spool.name == "app-errors-spool"


def test_frame_paths(reporter: Reporter) -> None:
    assert (
        _error_spool._short("/x/lib/python3.15/site-packages/gatelock/a.py", "m/")
        == "gatelock/a.py"
    )
    assert _error_spool._short(
        "/home/u/src/leetcode-guard/leetcode_guard/ui.py", "leetcode_guard/"
    ) == ("leetcode_guard/ui.py")
    assert _error_spool._short("/somewhere/else.py", "m/") == "else.py"


def test_slow_never_raises(reporter: Reporter, tmp_path: Path) -> None:
    (tmp_path / "leetcode-guard.jsonl").mkdir()
    reporter.slow("op", 2000, wait_id="w")
    assert True


def test_still_after_end_does_nothing(
    reporter: Reporter, tmp_path: Path, clock: Clock
) -> None:
    wait = reporter.begin("op")
    wait.end()
    clock.t += 9
    wait._still()
    assert spool_lines(tmp_path) == []
