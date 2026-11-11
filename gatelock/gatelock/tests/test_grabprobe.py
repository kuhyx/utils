# Copyright (c) 2026 Krzysztof Rudnicki
"""Tests for the non-blocking grab probe (:mod:`gatelock._grabprobe`).

Tk's ``grab -global`` blocks the whole event loop for ~1 s per FAILED attempt.
The probe asks X first, on a throwaway connection, so a lock whose grab is held
by someone else skips the Tk call instead of freezing its own UI. python-xlib
is replaced by an in-memory fake; ``scripts/verify_grab_responsive.py`` runs the
real thing against a real foreign grab.
"""

from __future__ import annotations

from dataclasses import replace
import logging
import tkinter as tk
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from gatelock._config import LockConfig
from gatelock._grabprobe import GrabProbe
from gatelock._prompts import PromptYield
from gatelock.tests.conftest import BOTH, build_loop, make_window

if TYPE_CHECKING:
    from collections.abc import Callable

OK, TAKEN, NOT_VIEWABLE = 0, 1, 3


class XError(Exception):
    """Stands in for ``Xlib.error.XError``."""


class DisplayError(Exception):
    """Stands in for ``Xlib.error.DisplayError``."""


class FakeRoot:
    """Answers grab requests from a script and records the ungrabs."""

    def __init__(self, keyboard: int, pointer: int) -> None:
        self.statuses = {"keyboard": keyboard, "pointer": pointer}
        self.asked: list[str] = []

    def grab_keyboard(self, *_args: object) -> int:
        self.asked.append("keyboard")
        return self.statuses["keyboard"]

    def grab_pointer(self, *_args: object) -> int:
        self.asked.append("pointer")
        if self.statuses["pointer"] < 0:
            message = "BadWindow"
            raise XError(message)
        return self.statuses["pointer"]


class FakeDisplay:
    """The slice of ``Xlib.display.Display`` the probe uses."""

    def __init__(self, root: FakeRoot) -> None:
        self.root = root
        self.ungrabbed: list[str] = []
        self.closed = False

    def screen(self) -> SimpleNamespace:
        return SimpleNamespace(root=self.root)

    def ungrab_keyboard(self, _time: int) -> None:
        self.ungrabbed.append("keyboard")

    def ungrab_pointer(self, _time: int) -> None:
        self.ungrabbed.append("pointer")

    def sync(self) -> None:
        self.ungrabbed.append("sync")

    def close(self) -> None:
        self.closed = True


def loaded(factory: Callable[[], FakeDisplay]) -> tuple[SimpleNamespace, ...]:
    """What ``load_xlib("Xlib.display", "Xlib.X", "Xlib.error")`` returns."""
    return (
        SimpleNamespace(Display=factory),
        SimpleNamespace(
            GrabSuccess=OK,
            AlreadyGrabbed=TAKEN,
            GrabModeAsync=1,
            CurrentTime=0,
            NONE=0,
        ),
        SimpleNamespace(
            DisplayError=DisplayError,
            XauthError=DisplayError,
            ConnectionClosedError=DisplayError,
            XError=XError,
        ),
    )


def probe_with(display: FakeDisplay) -> tuple[GrabProbe, object]:
    """A probe whose X connection is ``display`` (patch is the second item)."""
    patcher = patch(
        "gatelock._grabprobe.load_xlib", return_value=loaded(lambda: display)
    )
    patcher.start()
    return GrabProbe(), patcher


@pytest.fixture(autouse=True)
def _unpatch() -> object:
    yield
    patch.stopall()


class TestProbe:
    """What the probe reports, and that it leaves nothing grabbed."""

    def test_free_grab_is_released_at_once(self) -> None:
        """Nobody holds it: report free, and give the probe's own grab back."""
        display = FakeDisplay(FakeRoot(OK, OK))
        probe, _ = probe_with(display)
        assert probe.blocked() is None
        assert display.root.asked == ["keyboard", "pointer"]
        assert display.ungrabbed == ["keyboard", "pointer", "sync"]
        assert display.closed

    @pytest.mark.parametrize(
        ("keyboard", "pointer", "which"),
        [(TAKEN, OK, "keyboard"), (OK, TAKEN, "pointer")],
    )
    def test_foreign_grab_is_reported(
        self, keyboard: int, pointer: int, which: str
    ) -> None:
        """Either device held elsewhere blocks us; the reason names it."""
        display = FakeDisplay(FakeRoot(keyboard, pointer))
        probe, _ = probe_with(display)
        reason = probe.blocked()
        assert reason is not None
        assert "another application has grab" in reason
        assert which in reason
        assert display.ungrabbed[-1] == "sync"
        assert display.root.asked[-1] == which

    def test_other_statuses_defer_to_tk(self) -> None:
        """Not viewable and the like are not a foreign holder: let Tk decide."""
        display = FakeDisplay(FakeRoot(NOT_VIEWABLE, OK))
        probe, _ = probe_with(display)
        assert probe.blocked() is None

    def test_check_raises_tcl_error_when_blocked(self) -> None:
        """``check`` speaks Tk's dialect so callers keep one except clause."""
        probe, _ = probe_with(FakeDisplay(FakeRoot(TAKEN, OK)))
        with pytest.raises(tk.TclError, match="another application has grab"):
            probe.check()

    def test_check_is_silent_when_free(self) -> None:
        """Free grab: nothing raised."""
        probe, _ = probe_with(FakeDisplay(FakeRoot(OK, OK)))
        probe.check()


class TestFailClosed:
    """When X cannot be asked, fall back to today's behaviour: call Tk."""

    def test_missing_xlib(self, caplog: pytest.LogCaptureFixture) -> None:
        """No python-xlib: unknown, said once."""
        probe = GrabProbe()
        with (
            patch("gatelock._grabprobe.load_xlib", return_value=None),
            caplog.at_level(logging.WARNING),
        ):
            assert probe.blocked() is None
            assert probe.blocked() is None
        assert caplog.text.count("python-xlib") == 1

    def test_no_connection(self, caplog: pytest.LogCaptureFixture) -> None:
        """A connection that will not open: unknown, warned."""

        def refuse() -> FakeDisplay:
            message = "no display"
            raise DisplayError(message)

        probe = GrabProbe()
        with (
            patch("gatelock._grabprobe.load_xlib", return_value=loaded(refuse)),
            caplog.at_level(logging.WARNING),
        ):
            assert probe.blocked() is None
        assert "X connection" in caplog.text

    def test_request_error_still_closes(self, caplog: pytest.LogCaptureFixture) -> None:
        """An X error mid-probe: unknown, warned, connection dropped."""
        display = FakeDisplay(FakeRoot(OK, -1))
        probe, _ = probe_with(display)
        with caplog.at_level(logging.WARNING):
            assert probe.blocked() is None
        assert "BadWindow" in caplog.text
        assert display.closed


class TestWiring:
    """The probe gates every global-grab attempt, in arming and in recovery."""

    def test_policy_exposes_check_grab(self) -> None:
        """``PromptYield.check_grab`` is the one entry point."""
        probe = MagicMock()
        PromptYield(grab_probe=probe).check_grab()
        probe.check.assert_called_once_with()

    def test_arming_skips_tk_when_blocked(self, mock_root: MagicMock) -> None:
        """A foreign holder: the 1 s Tk call is never made, the reason is kept."""
        window, _ = make_window(mock_root, config=LockConfig(mode="hard"))
        policy = PromptYield(grab_probe=MagicMock())
        policy._grab_probe.check.side_effect = tk.TclError("held")
        window._arming = replace(window._arming, prompt_yield=policy)
        window._acquire_global_grab(attempt=1)
        mock_root.grab_set_global.assert_not_called()
        assert policy.last_reason == "held"
        mock_root.after.assert_called()

    def test_recovery_skips_tk_when_blocked(self, mock_root: MagicMock) -> None:
        """Same in the recovery tick."""
        recovery, enumerator, _ = build_loop(mock_root, LockConfig(mode="hard"))
        enumerator.scan.return_value = BOTH
        mock_root.grab_current.return_value = None
        policy = PromptYield(grab_probe=MagicMock())
        policy._grab_probe.check.side_effect = tk.TclError("held")
        recovery._parts = recovery._parts.__class__(
            **{**vars(recovery._parts), "prompt_yield": policy}
        )
        report = recovery.tick()
        mock_root.grab_set_global.assert_not_called()
        assert report.grab_reasserted is False
        assert policy.last_reason == "held"
