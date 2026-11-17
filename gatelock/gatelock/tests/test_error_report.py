# Copyright (c) 2026 Krzysztof Rudnicki
"""The error reporter's process hooks: excepthooks, Tk callbacks, stalls."""

from __future__ import annotations

import sys
import threading
import tkinter as tk
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from gatelock import error_report
from gatelock._error_spool import Reporter
from gatelock.tests.errorkit import Clock, raised, spool_lines

if TYPE_CHECKING:
    from collections.abc import Iterator
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


DOOR = "_report_exception"


def _key_error() -> None:
    key = "cb"
    raise KeyError(key)


@pytest.fixture
def hooks() -> Iterator[None]:
    saved = (sys.excepthook, threading.excepthook, getattr(tk.Misc, DOOR))
    yield
    sys.excepthook, threading.excepthook = saved[:2]
    setattr(tk.Misc, DOOR, saved[2])
    error_report.INSTALLED.reporter = None


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
    exc = raised()
    sys.excepthook(ValueError, exc, exc.__traceback__)
    prior.assert_called_once()
    args = MagicMock(
        exc_type=RuntimeError, exc_value=RuntimeError("thread boom"), exc_traceback=None
    )
    threading.excepthook(args)
    prior_thread.assert_called_once_with(args)
    kinds = [e["kind"] for e in spool_lines(tmp_path, "tk-app")]
    assert kinds == ["uncaught.python", "uncaught.thread"]


def test_thread_hook_without_value(hooks: None, tmp_path: Path) -> None:
    threading.excepthook = MagicMock()
    _install(tmp_path)
    threading.excepthook(
        MagicMock(exc_type=SystemExit, exc_value=None, exc_traceback=None)
    )
    assert spool_lines(tmp_path, "tk-app")[0]["error"] == "SystemExit"


def test_install_reports_tk_callback_errors(hooks: None, tmp_path: Path) -> None:
    prior = MagicMock()
    setattr(tk.Misc, DOOR, prior)
    _install(tmp_path)
    widget = MagicMock()
    try:
        _key_error()
    except KeyError:
        getattr(tk.Misc, DOOR)(widget)
    prior.assert_called_once_with(widget)
    (entry,) = spool_lines(tmp_path, "tk-app")
    assert entry["kind"] == "uncaught.tk"
    assert entry["error"] == "KeyError: 'cb'"


def test_tk_hook_without_active_exception(hooks: None, tmp_path: Path) -> None:
    setattr(tk.Misc, DOOR, MagicMock())
    _install(tmp_path)
    getattr(tk.Misc, DOOR)(MagicMock())
    assert spool_lines(tmp_path, "tk-app") == []


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
    (entry,) = spool_lines(tmp_path)
    assert entry["operation"] == "tk.mainloop"
    assert entry["durationMs"] == 2500 - error_report.STALL_TICK_MS


def test_stall_watch_stops_with_the_window(reporter: Reporter, clock: Clock) -> None:
    root = MagicMock()
    error_report.watch_stalls(root, reporter)
    tick = root.after.call_args.args[1]
    root.after.side_effect = tk.TclError("destroyed")
    tick()  # must not raise
    assert root.after.call_count == 2
