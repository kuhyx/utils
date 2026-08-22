"""Tests for what the recovery loop re-asserts on each tick.

Split from ``test_recovery.py`` (250-line cap). That file keeps the static
invariant, the 2026-07-25 monotonic-sequence walk, the tick mechanics and
scheduling; this one covers the three things a tick re-asserts -- the input
grab, focus, and VT switching -- and the branches within each.

The ``loop`` fixture and the output scans both halves drive come from
``conftest.py``.
"""

from __future__ import annotations

import logging
import tkinter as tk
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from gatelock._window import LockConfig
from gatelock.tests.conftest import BOTH, DEAD_PRIMARY, build_loop

if TYPE_CHECKING:
    import pytest

    from gatelock._recovery import RecoveryLoop
    from gatelock._surfaces import SurfaceSet


class TestGrabReassertion:
    """Re-taking a lost grab, never releasing one."""

    def test_reasserts_when_lost(
        self, loop: tuple[RecoveryLoop, MagicMock, SurfaceSet], mock_root: MagicMock
    ) -> None:
        """Something stole the grab; we take it back."""
        recovery, enumerator, _surfaces = loop
        enumerator.scan.return_value = BOTH
        mock_root.grab_current.return_value = None
        report = recovery.tick()
        assert report.grab_reasserted is True
        mock_root.grab_set_global.assert_called()

    def test_noop_when_still_held(
        self, loop: tuple[RecoveryLoop, MagicMock, SurfaceSet], mock_root: MagicMock
    ) -> None:
        """Holding the grab already means no work."""
        recovery, enumerator, _surfaces = loop
        enumerator.scan.return_value = BOTH
        mock_root.grab_current.return_value = mock_root
        assert recovery.tick().grab_reasserted is False

    def test_noop_when_our_own_child_holds_the_grab(
        self, loop: tuple[RecoveryLoop, MagicMock, SurfaceSet], mock_root: MagicMock
    ) -> None:
        """A posted menu owns the grab; we must not steal it back.

        Regression: the old ``grab_current() is root`` test read a Tk menu's
        own grab as "lost" and re-grabbed a second later, which made the
        screen-locker sport selector unusable while locked.
        """
        recovery, enumerator, _surfaces = loop
        enumerator.scan.return_value = BOTH
        mock_root.grab_current.return_value = MagicMock(name="posted menu")
        assert recovery.tick().grab_reasserted is False
        mock_root.grab_set_global.assert_not_called()

    def test_reasserts_when_the_holder_is_not_one_of_our_windows(
        self,
        loop: tuple[RecoveryLoop, MagicMock, SurfaceSet],
        mock_root: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Fail closed: a name we cannot resolve is not provably ours.

        A ``ttk.Combobox`` popdown is a Tcl-created toplevel absent from
        Tkinter's widget map, so ``nametowidget`` raises ``KeyError``. Keeping
        the lock beats keeping a banned widget's popdown.
        """
        recovery, enumerator, _surfaces = loop
        enumerator.scan.return_value = BOTH
        mock_root.grab_current.side_effect = KeyError("!popdown")
        with caplog.at_level(logging.WARNING):
            assert recovery.tick().grab_reasserted is True
        mock_root.grab_set_global.assert_called()
        assert "not one of our windows" in caplog.text

    def test_a_persistent_lost_grab_warns_once_not_once_per_tick(
        self,
        loop: tuple[RecoveryLoop, MagicMock, SurfaceSet],
        mock_root: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A state that lasts the whole lock must not stream to the journal."""
        recovery, enumerator, _surfaces = loop
        enumerator.scan.return_value = BOTH
        mock_root.grab_current.side_effect = tk.TclError("gone")
        with caplog.at_level(logging.WARNING):
            for _ in range(5):
                recovery.tick()
        lost = [r for r in caplog.records if "current grab" in r.message]
        assert len(lost) == 1, f"warned {len(lost)} times over 5 ticks"

    def test_tclerror_while_regrabbing_is_swallowed(
        self, loop: tuple[RecoveryLoop, MagicMock, SurfaceSet], mock_root: MagicMock
    ) -> None:
        """A failed re-grab is retried next tick, not raised."""
        recovery, enumerator, _surfaces = loop
        enumerator.scan.return_value = BOTH
        mock_root.grab_current.return_value = None
        mock_root.grab_set_global.side_effect = tk.TclError("held")
        assert recovery.tick().grab_reasserted is False

    def test_grab_query_tclerror(
        self, loop: tuple[RecoveryLoop, MagicMock, SurfaceSet], mock_root: MagicMock
    ) -> None:
        """A TclError querying the grab counts as not holding it."""
        recovery, enumerator, _surfaces = loop
        enumerator.scan.return_value = BOTH
        mock_root.grab_current.side_effect = tk.TclError("gone")
        assert recovery.tick().grab_reasserted is True

    def test_no_reassert_when_grab_not_global(self, mock_root: MagicMock) -> None:
        """Soft mode takes no grab, so there is nothing to re-assert."""
        recovery, enumerator, _surfaces = build_loop(mock_root, LockConfig(mode="soft"))
        enumerator.scan.return_value = BOTH
        assert recovery.tick().grab_reasserted is False


class TestFocusReassertion:
    """Re-focusing a surface that was (re)built after the first tick.

    Regression coverage for the 2026-08 bug: a monitor blip tears down and
    rebuilds a surface's widgets mid-lock, but ``LockWindow`` only ever
    focuses the entry once, on first grab acquisition. Without this, the new
    widget renders correctly but is never the Tk focus target, and the held
    global grab means nothing else can take focus either -- a silent,
    permanent input dead end that looks identical to a working lock.
    """

    def test_refocuses_when_a_surface_is_recreated(
        self, loop: tuple[RecoveryLoop, MagicMock, SurfaceSet]
    ) -> None:
        """A surface coming back live re-triggers on_focus_ready."""
        recovery, enumerator, surfaces = loop
        hooks = surfaces._builder
        enumerator.scan.return_value = BOTH
        recovery.tick()
        hooks.on_focus_ready.reset_mock()
        enumerator.scan.return_value = DEAD_PRIMARY
        recovery.tick()
        enumerator.scan.return_value = BOTH
        recovery.tick()
        hooks.on_focus_ready.assert_called_once()

    def test_no_refocus_when_nothing_was_created(
        self, loop: tuple[RecoveryLoop, MagicMock, SurfaceSet]
    ) -> None:
        """A tick with no new surfaces must not fight the user mid-typing."""
        recovery, enumerator, surfaces = loop
        hooks = surfaces._builder
        enumerator.scan.return_value = BOTH
        recovery.tick()
        hooks.on_focus_ready.reset_mock()
        recovery.tick()
        hooks.on_focus_ready.assert_not_called()

    def test_tclerror_during_refocus_is_swallowed(
        self, loop: tuple[RecoveryLoop, MagicMock, SurfaceSet], mock_root: MagicMock
    ) -> None:
        """A focus call on a half-torn-down widget must not crash the tick."""
        recovery, enumerator, surfaces = loop
        hooks = surfaces._builder
        hooks.on_focus_ready.side_effect = tk.TclError("gone")
        enumerator.scan.return_value = BOTH
        recovery.tick()


class TestVtReassertion:
    """Periodically re-disabling VT switching, never re-enabling it."""

    def test_reasserts_on_the_thirtieth_tick(
        self, loop: tuple[RecoveryLoop, MagicMock, SurfaceSet]
    ) -> None:
        """VT is re-disabled every 30 ticks."""
        recovery, enumerator, _surfaces = loop
        enumerator.scan.return_value = BOTH
        with patch("gatelock._recovery.disable_vt_switching") as vt:
            reports = [recovery.tick() for _ in range(30)]
        assert [i for i, r in enumerate(reports, 1) if r.vt_reasserted] == [30]
        vt.assert_called_once_with()

    def test_never_when_vt_not_managed(self, mock_root: MagicMock) -> None:
        """An app that does not disable VT never re-asserts it."""
        recovery, enumerator, _surfaces = build_loop(mock_root, LockConfig(mode="soft"))
        enumerator.scan.return_value = BOTH
        assert all(not recovery.tick().vt_reasserted for _ in range(31))
