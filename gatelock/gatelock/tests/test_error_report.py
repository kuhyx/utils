# Copyright (c) 2026 Krzysztof Rudnicki
"""The Tk app error and slow-wait reporter: hooks, dedup, spool lines, stalls."""

from __future__ import annotations

import json
import sys
import threading
import tkinter as tk
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from gatelock import error_report
from gatelock.error_report import Reporter

DOOR = "_report_exception"

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


class Clock:
    """A settable wall + monotonic clock."""

    def __init__(self) -> None:
        self.t = 1_800_000_000.0

    def __call__(self) -> float:
        return self.t


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


def _lines(tmp_path: Path, app: str = "leetcode-guard") -> list[dict[str, object]]:
    path = tmp_path / f"{app}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


def _raise() -> BaseException:
    try:
        raise ValueError("bad 12")  # noqa: EM101, TRY003, TRY301 -- a real traceback for the test
    except ValueError as e:
        return e


def test_report_writes_one_entry(reporter: Reporter, tmp_path: Path) -> None:
    exc = _raise()
    reporter.report("uncaught.python", exc, exc.__traceback__)
    (entry,) = _lines(tmp_path)
    assert entry["kind"] == "uncaught.python"
    assert entry["error"] == "ValueError: bad 12"
    assert entry["repo"] == "kuhyx/leetcode-guard"
    assert entry["mark"] == "leetcode_guard/"
    assert entry["build"] == 5
    assert entry["version"] == "0.3.0"
    assert entry["at"] == "2027-01-15T08:00:00.000Z"
    stack = entry["stack"]
    assert isinstance(stack, list)
    assert "test_error_report.py" in stack[0]
    assert " in _raise" in stack[0]


def test_identical_errors_within_window_are_dropped(
    reporter: Reporter, tmp_path: Path, clock: Clock
) -> None:
    for _ in range(5):
        reporter.report("k", "same")
    assert len(_lines(tmp_path)) == 1
    clock.t += Reporter.WINDOW + 1
    reporter.report("k", "same")
    assert len(_lines(tmp_path)) == 2


def test_rate_cap_per_minute(reporter: Reporter, tmp_path: Path, clock: Clock) -> None:
    for i in range(Reporter.MAX_PER_MINUTE + 5):
        reporter.report("k", f"e{i}")
    assert len(_lines(tmp_path)) == Reporter.MAX_PER_MINUTE
    clock.t += 61
    reporter.report("k", "later")
    assert len(_lines(tmp_path)) == Reporter.MAX_PER_MINUTE + 1


def test_report_never_raises(reporter: Reporter, tmp_path: Path) -> None:
    class Bad:
        def __str__(self) -> str:
            raise RuntimeError

    reporter.report("k", Bad())
    (tmp_path / "leetcode-guard.jsonl").mkdir()  # an unwritable spool file
    reporter.report("k", "other")
    assert True


def test_report_inside_report_is_ignored(reporter: Reporter, tmp_path: Path) -> None:
    reporter._busy = True
    reporter.report("k", "x")
    assert _lines(tmp_path) == []


def test_slow_wait_over_threshold_is_written(
    reporter: Reporter, tmp_path: Path, clock: Clock
) -> None:
    wait = reporter.begin("coach.load", route="coach")
    clock.t += 2.0
    wait.end()
    wait.end()  # repeat ends do nothing
    (entry,) = _lines(tmp_path)
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
    assert _lines(tmp_path) == []


def test_still_waiting_is_written_then_the_end(
    reporter: Reporter, tmp_path: Path, clock: Clock
) -> None:
    wait = reporter.begin("hung")
    clock.t += 6
    wait._still()
    clock.t += 1
    wait.end()
    still, end = _lines(tmp_path)
    assert still["still"] is True
    assert end["still"] is False
    assert still["waitId"] == end["waitId"]


def test_slow_rate_cap(reporter: Reporter, tmp_path: Path, clock: Clock) -> None:
    for _ in range(Reporter.MAX_SLOW_PER_MINUTE + 3):
        w = reporter.begin("op")
        clock.t += 1.5
        w.end()
    assert len(_lines(tmp_path)) == Reporter.MAX_SLOW_PER_MINUTE


@pytest.fixture
def hooks() -> Iterator[None]:
    saved = (sys.excepthook, threading.excepthook, getattr(tk.Misc, DOOR))
    yield
    sys.excepthook, threading.excepthook = saved[:2]
    setattr(tk.Misc, DOOR, saved[2])
    error_report._installed = None


def _install(spool: Path) -> Reporter:
    rep = error_report.install("tk-app", "kuhyx/tk-app")
    rep.spool = spool
    return rep


def test_install_chains_sys_and_thread_hooks(hooks: None, tmp_path: Path) -> None:
    prior = MagicMock()
    sys.excepthook = prior
    prior_thread = MagicMock()
    threading.excepthook = prior_thread
    rep = _install(tmp_path)
    assert _install(tmp_path) is rep  # idempotent
    exc = _raise()
    sys.excepthook(ValueError, exc, exc.__traceback__)
    prior.assert_called_once()
    args = MagicMock(
        exc_type=RuntimeError, exc_value=RuntimeError("thread boom"), exc_traceback=None
    )
    threading.excepthook(args)
    prior_thread.assert_called_once_with(args)
    kinds = [e["kind"] for e in _lines(tmp_path, "tk-app")]
    assert kinds == ["uncaught.python", "uncaught.thread"]


def test_thread_hook_without_value(hooks: None, tmp_path: Path) -> None:
    threading.excepthook = MagicMock()
    _install(tmp_path)
    threading.excepthook(
        MagicMock(exc_type=SystemExit, exc_value=None, exc_traceback=None)
    )
    assert _lines(tmp_path, "tk-app")[0]["error"] == "SystemExit"


def test_install_reports_tk_callback_errors(hooks: None, tmp_path: Path) -> None:
    prior = MagicMock()
    setattr(tk.Misc, DOOR, prior)
    _install(tmp_path)
    widget = MagicMock()
    try:
        raise KeyError("cb")  # noqa: EM101, TRY301
    except KeyError:
        getattr(tk.Misc, DOOR)(widget)
    prior.assert_called_once_with(widget)
    (entry,) = _lines(tmp_path, "tk-app")
    assert entry["kind"] == "uncaught.tk"
    assert entry["error"] == "KeyError: 'cb'"


def test_tk_hook_without_active_exception(hooks: None, tmp_path: Path) -> None:
    setattr(tk.Misc, DOOR, MagicMock())
    _install(tmp_path)
    getattr(tk.Misc, DOOR)(MagicMock())
    assert _lines(tmp_path, "tk-app") == []


def test_default_spool_and_mark(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    rep = Reporter(app="diet-guard", repo="kuhyx/diet-guard")
    assert rep.spool == tmp_path / "app-errors-spool"
    assert rep.mark == "diet_guard/"
    monkeypatch.delenv("XDG_STATE_HOME")
    assert Reporter(app="a", repo="kuhyx/a").spool.name == "app-errors-spool"


def test_stall_watch_reports_a_frozen_loop(
    reporter: Reporter, tmp_path: Path, clock: Clock
) -> None:
    root = MagicMock()
    error_report.watch_stalls(root, reporter)
    tick = root.after.call_args.args[1]
    clock.t += 0.1
    tick()  # on time: nothing
    clock.t += 2.5  # the loop was blocked 2.5 s
    tick()
    (entry,) = _lines(tmp_path)
    assert entry["operation"] == "tk.mainloop"
    assert entry["durationMs"] == 2500 - error_report.STALL_TICK_MS


def test_stall_watch_stops_with_the_window(reporter: Reporter, clock: Clock) -> None:
    root = MagicMock()
    error_report.watch_stalls(root, reporter)
    tick = root.after.call_args.args[1]
    root.after.side_effect = tk.TclError("destroyed")
    tick()  # must not raise
    assert root.after.call_count == 2


def test_frame_paths(reporter: Reporter) -> None:
    assert (
        error_report._short("/x/lib/python3.15/site-packages/gatelock/a.py", "m/")
        == "gatelock/a.py"
    )
    assert error_report._short(
        "/home/u/src/leetcode-guard/leetcode_guard/ui.py", "leetcode_guard/"
    ) == ("leetcode_guard/ui.py")
    assert error_report._short("/somewhere/else.py", "m/") == "else.py"


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
    assert _lines(tmp_path) == []
