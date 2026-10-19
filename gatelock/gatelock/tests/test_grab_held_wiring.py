# Copyright (c) 2026 Krzysztof Rudnicki
"""Tests for WHEN ``grab_held`` flips: only on a grab that actually succeeded.

The arming sequence reports a held grab after ``grab_set``/``grab_set_global``
returns; the recovery loop reports each tick's real answer (so a grab a game
stole reads False until it is re-taken); ``LockWindow.report_grab_held`` is the
public hook an app that suspends its lock (leetcode-guard) uses.
"""

from __future__ import annotations

from dataclasses import replace
import tkinter as tk
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, call

from gatelock._config import GrabPolicy, LockConfig
from gatelock._window import LockWindow
from gatelock.tests.conftest import BOTH

if TYPE_CHECKING:
    from gatelock._recovery import RecoveryLoop
    from gatelock._surfaces import SurfaceSet


def _window(root: MagicMock, config: LockConfig) -> tuple[LockWindow, MagicMock]:
    arbiter = MagicMock()
    return LockWindow(root, config, MagicMock(), arbiter=arbiter), arbiter


class TestArming:
    """The first grab reports held only once it succeeded."""

    def test_global_success_reports_held(self, mock_root: MagicMock) -> None:
        """grab_set_global returned: held."""
        window, arbiter = _window(mock_root, LockConfig(mode="hard"))
        window._acquire_global_grab(attempt=1)
        arbiter.set_grab_held.assert_called_once_with(held=True)

    def test_global_failure_with_retry_reports_nothing(
        self, mock_root: MagicMock
    ) -> None:
        """Still retrying (a game holds it): not held, nothing written."""
        mock_root.grab_set_global.side_effect = tk.TclError("held")
        window, arbiter = _window(mock_root, LockConfig(mode="hard"))
        window._acquire_global_grab(attempt=1)
        arbiter.set_grab_held.assert_not_called()

    def test_local_fallback_reports_held_only_on_success(
        self, mock_root: MagicMock
    ) -> None:
        """retry_ms=0 falls back to a local grab; held iff that worked."""
        mock_root.grab_set_global.side_effect = tk.TclError("held")
        config = LockConfig(mode="hard", grab=GrabPolicy(retry_ms=0))
        window, arbiter = _window(mock_root, config)
        window._acquire_global_grab(attempt=1)
        arbiter.set_grab_held.assert_called_once_with(held=True)

        mock_root.grab_set.side_effect = tk.TclError("also gone")
        window, arbiter = _window(mock_root, config)
        window._acquire_global_grab(attempt=1)
        arbiter.set_grab_held.assert_not_called()

    def test_configured_local_grab(self, mock_root: MagicMock) -> None:
        """A local-grab lock reports held after grab_set, not before."""
        config = LockConfig(mode="soft", grab=GrabPolicy(kind="local"))
        window, arbiter = _window(mock_root, config)
        window.grab_input()
        arbiter.set_grab_held.assert_called_once_with(held=True)

        mock_root.grab_set.side_effect = tk.TclError("no")
        window, arbiter = _window(mock_root, config)
        window.grab_input()
        arbiter.set_grab_held.assert_not_called()


def _spy(recovery: RecoveryLoop) -> MagicMock:
    """Swap the loop's grab-state callback for a mock."""
    spy = MagicMock()
    recovery._parts = replace(recovery._parts, on_grab_held=spy)
    return spy


class TestRecovery:
    """Each tick reports whether the grab is really ours."""

    def test_reports_true_while_held(
        self, loop: tuple[RecoveryLoop, MagicMock, SurfaceSet], mock_root: MagicMock
    ) -> None:
        """Held grab -> True (deduplicated downstream)."""
        recovery, enumerator, _ = loop
        spy = _spy(recovery)
        enumerator.scan.return_value = BOTH
        mock_root.grab_current.return_value = mock_root
        recovery.tick()
        spy.assert_called_once_with(held=True)

    def test_stolen_and_not_retaken_reports_false(
        self, loop: tuple[RecoveryLoop, MagicMock, SurfaceSet], mock_root: MagicMock
    ) -> None:
        """Lost and the re-grab failed: False, the truth."""
        recovery, enumerator, _ = loop
        spy = _spy(recovery)
        enumerator.scan.return_value = BOTH
        mock_root.grab_current.return_value = None
        mock_root.grab_set_global.side_effect = tk.TclError("game")
        assert recovery.tick().grab_reasserted is False
        spy.assert_called_once_with(held=False)

    def test_retaken_reports_true(
        self, loop: tuple[RecoveryLoop, MagicMock, SurfaceSet], mock_root: MagicMock
    ) -> None:
        """Lost then re-taken in the same tick: True."""
        recovery, enumerator, _ = loop
        spy = _spy(recovery)
        enumerator.scan.return_value = BOTH
        mock_root.grab_current.return_value = None
        assert recovery.tick().grab_reasserted is True
        spy.assert_called_once_with(held=True)


class TestWindowHook:
    """``LockWindow.report_grab_held`` forwards to the arbiter, if any."""

    def test_forwards_both_directions(self, mock_root: MagicMock) -> None:
        """Study mode's release and resume land on the claim."""
        window, arbiter = _window(mock_root, LockConfig(mode="hard"))
        window.report_grab_held(held=False)
        window.report_grab_held(held=True)
        assert arbiter.set_grab_held.call_args_list == [
            call(held=False),
            call(held=True),
        ]

    def test_recovery_reports_reach_the_arbiter(self, mock_root: MagicMock) -> None:
        """The loop the window builds is wired to the same hook."""
        window, arbiter = _window(mock_root, LockConfig(mode="hard"))
        mock_root.grab_current.return_value = None
        mock_root.grab_set_global.side_effect = tk.TclError("game")
        window.recovery._reassert_grab()
        arbiter.set_grab_held.assert_called_once_with(held=False)

    def test_no_arbiter_is_a_noop(self, mock_root: MagicMock) -> None:
        """Arbitration disabled: nothing to write, nothing raised."""
        window = LockWindow(mock_root, LockConfig(mode="hard"), MagicMock())
        window.report_grab_held(held=True)
