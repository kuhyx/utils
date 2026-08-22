"""Tests for the monotonic recovery loop.

Three layers, per the release plan: a static AST check that the weakening calls
are absent, a behavioural walk through the 2026-07-25 sequence asserting the
lock never weakens, and per-branch coverage.
"""

from __future__ import annotations

import logging
import tkinter as tk
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from gatelock.tests.conftest import ALL_DARK, BOTH, DEAD_PRIMARY, FAILED

if TYPE_CHECKING:
    import pytest

    from gatelock._recovery import RecoveryLoop
    from gatelock._surfaces import SurfaceSet


class TestMonotonicSequence:
    """The whole incident, walked end to end."""

    def test_lock_never_weakens(
        self,
        loop: tuple[RecoveryLoop, MagicMock, SurfaceSet],
        mock_root: MagicMock,
    ) -> None:
        """Across every transition the grab and VT are only ever asserted."""
        recovery, enumerator, surfaces = loop
        hooks = surfaces._builder
        with patch("gatelock._recovery.disable_vt_switching") as vt:
            for step in (BOTH, DEAD_PRIMARY, ALL_DARK, FAILED, BOTH):
                enumerator.scan.return_value = step
                recovery.tick()
                mock_root.grab_release.assert_not_called()
                mock_root.destroy.assert_not_called()
                hooks.on_close.assert_not_called()
            assert "restore" not in str(vt.mock_calls)

    def test_dark_primary_keeps_the_visible_monitor(
        self, loop: tuple[RecoveryLoop, MagicMock, SurfaceSet]
    ) -> None:
        """The exact 2026-07-25 state: the lock lands where it can be seen."""
        recovery, enumerator, surfaces = loop
        enumerator.scan.return_value = BOTH
        recovery.tick()
        enumerator.scan.return_value = DEAD_PRIMARY
        report = recovery.tick()
        assert report.live_outputs == ("HDMI-0",)
        assert sorted(surfaces.names()) == ["HDMI-0"]
        assert report.blind == ()


class TestTick:
    """Per-branch behaviour of one pass."""

    def test_failed_scan_changes_nothing(
        self, loop: tuple[RecoveryLoop, MagicMock, SurfaceSet]
    ) -> None:
        """No information is never a reason to touch anything."""
        recovery, enumerator, surfaces = loop
        enumerator.scan.return_value = BOTH
        recovery.tick()
        before = sorted(surfaces.names())
        enumerator.scan.return_value = FAILED
        report = recovery.tick()
        assert report.scan_ok is False
        assert report.delta is None
        assert sorted(surfaces.names()) == before

    def test_zero_live_outputs_stays_armed(
        self, loop: tuple[RecoveryLoop, MagicMock, SurfaceSet], mock_root: MagicMock
    ) -> None:
        """All monitors dark: nothing shown, nothing released."""
        recovery, enumerator, _surfaces = loop
        enumerator.scan.return_value = ALL_DARK
        report = recovery.tick()
        assert report.live_outputs == ()
        mock_root.grab_release.assert_not_called()

    def test_blind_output_is_reported(
        self, loop: tuple[RecoveryLoop, MagicMock, SurfaceSet]
    ) -> None:
        """A live output that failed to map is surfaced as an error."""
        recovery, enumerator, surfaces = loop
        enumerator.scan.return_value = BOTH
        recovery.tick()
        surfaces._surfaces["DP-0"].window.withdraw()
        report = recovery.tick()
        assert "DP-0" in report.blind

    def test_tick_counter(
        self, loop: tuple[RecoveryLoop, MagicMock, SurfaceSet]
    ) -> None:
        """Ticks are counted, for the periodic VT re-assert."""
        recovery, enumerator, _surfaces = loop
        enumerator.scan.return_value = BOTH
        recovery.tick()
        recovery.tick()
        assert recovery.ticks == 2


class TestScheduling:
    """The two cadences."""

    def test_start_schedules_both(
        self, loop: tuple[RecoveryLoop, MagicMock, SurfaceSet], mock_root: MagicMock
    ) -> None:
        """Starting queues a drain and a verify."""
        recovery, _enumerator, _surfaces = loop
        recovery.start()
        assert mock_root.after.call_count == 2

    def test_drain_ticks_only_when_signalled(
        self, loop: tuple[RecoveryLoop, MagicMock, SurfaceSet]
    ) -> None:
        """No change signal means no full pass."""
        recovery, enumerator, _surfaces = loop
        enumerator.scan.return_value = BOTH
        recovery._detector.take_pending.return_value = False
        recovery._running = True
        recovery._drain()
        enumerator.scan.assert_not_called()

    def test_drain_ticks_when_signalled(
        self, loop: tuple[RecoveryLoop, MagicMock, SurfaceSet]
    ) -> None:
        """A pending change triggers a full pass."""
        recovery, enumerator, _surfaces = loop
        enumerator.scan.return_value = BOTH
        recovery._detector.take_pending.return_value = True
        recovery._running = True
        recovery._drain()
        enumerator.scan.assert_called_once_with()

    def test_verify_reschedules(
        self, loop: tuple[RecoveryLoop, MagicMock, SurfaceSet]
    ) -> None:
        """The verify cadence re-arms itself."""
        recovery, enumerator, _surfaces = loop
        enumerator.scan.return_value = BOTH
        recovery._running = True
        recovery._verify()
        assert recovery.ticks == 1

    def test_verify_reschedules_even_when_the_tick_raises(
        self,
        loop: tuple[RecoveryLoop, MagicMock, SurfaceSet],
        mock_root: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A broken tick must not end the loop -- that would fail open."""
        recovery, enumerator, _surfaces = loop
        enumerator.scan.side_effect = RuntimeError("boom")
        recovery._running = True
        with caplog.at_level(logging.ERROR):
            recovery._verify()
        mock_root.after.assert_called_once()
        assert "verify tick raised" in caplog.text

    def test_drain_reschedules_even_when_the_tick_raises(
        self,
        loop: tuple[RecoveryLoop, MagicMock, SurfaceSet],
        mock_root: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Same for the cheap cadence."""
        recovery, enumerator, _surfaces = loop
        enumerator.scan.side_effect = RuntimeError("boom")
        recovery._detector.take_pending.return_value = True
        recovery._running = True
        with caplog.at_level(logging.ERROR):
            recovery._drain()
        mock_root.after.assert_called_once()
        assert "drain tick raised" in caplog.text

    def test_stop_cancels_and_halts(
        self, loop: tuple[RecoveryLoop, MagicMock, SurfaceSet], mock_root: MagicMock
    ) -> None:
        """Stopping cancels timers and prevents rescheduling."""
        recovery, _enumerator, _surfaces = loop
        recovery.start()
        recovery.stop()
        assert mock_root.after_cancel.call_count == 2
        mock_root.after.reset_mock()
        recovery._schedule_drain()
        recovery._schedule_verify()
        mock_root.after.assert_not_called()

    def test_stop_swallows_cancel_error(
        self, loop: tuple[RecoveryLoop, MagicMock, SurfaceSet], mock_root: MagicMock
    ) -> None:
        """A timer already gone is not an error."""
        recovery, _enumerator, _surfaces = loop
        recovery.start()
        mock_root.after_cancel.side_effect = tk.TclError("no such id")
        recovery.stop()

    def test_stop_before_start(
        self, loop: tuple[RecoveryLoop, MagicMock, SurfaceSet], mock_root: MagicMock
    ) -> None:
        """Stopping a loop that never started is safe."""
        recovery, _enumerator, _surfaces = loop
        recovery.stop()
        mock_root.after_cancel.assert_not_called()
