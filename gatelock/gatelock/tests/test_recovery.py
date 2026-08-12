"""Tests for the monotonic recovery loop.

Three layers, per the release plan: a static AST check that the weakening calls
are absent, a behavioural walk through the 2026-07-25 sequence asserting the
lock never weakens, and per-branch coverage.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path
import tkinter as tk
from unittest.mock import MagicMock, patch

import pytest

from gatelock._outputs import Output, OutputRect, OutputScan
from gatelock._recovery import RecoveryCollaborators, RecoveryLoop
from gatelock._surfaces import SurfaceSet
from gatelock._window import LockConfig

DP0 = Output("DP-0", connected=True, rect=OutputRect(0, 0, 3840, 2160), primary=True)
HDMI = Output("HDMI-0", connected=True, rect=OutputRect(3840, 0, 2560, 1440))
DP0_DARK = Output("DP-0", connected=True, rect=None, primary=True)
HDMI_DARK = Output("HDMI-0", connected=True, rect=None)

BOTH = OutputScan((DP0, HDMI), "randr", ok=True)
DEAD_PRIMARY = OutputScan((DP0_DARK, HDMI), "randr", ok=True)
ALL_DARK = OutputScan((DP0_DARK, HDMI_DARK), "randr", ok=True)
FAILED = OutputScan((), "none", ok=False)

WEAKENING_CALLS = frozenset(
    {"grab_release", "restore_vt_switching", "close", "destroy", "quit", "withdraw"}
)
SOURCE_ROOT = Path(__file__).resolve().parent.parent


def symbols(module: str) -> set[str]:
    """Every attribute and name referenced in a module's source."""
    tree = ast.parse((SOURCE_ROOT / module).read_text(encoding="utf-8"))
    return {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | {
        n.id for n in ast.walk(tree) if isinstance(n, ast.Name)
    }


@pytest.fixture
def loop(mock_root: MagicMock) -> tuple[RecoveryLoop, MagicMock, SurfaceSet]:
    """A recovery loop over mocked surroundings."""
    config = LockConfig(mode="hard")
    hooks = MagicMock()
    surfaces = SurfaceSet(mock_root, config, hooks)
    enumerator = MagicMock()
    detector = MagicMock()
    return (
        RecoveryLoop(
            mock_root,
            RecoveryCollaborators(
                config=config,
                surfaces=surfaces,
                enumerator=enumerator,
                detector=detector,
                hooks=hooks,
            ),
        ),
        enumerator,
        surfaces,
    )


class TestStaticInvariant:
    """The separation that makes monotonicity mechanical rather than hoped-for."""

    def test_recovery_contains_no_weakening_call(self) -> None:
        """_recovery.py must not be able to release, restore or destroy."""
        assert symbols("_recovery.py") & WEAKENING_CALLS == set()

    def test_recovery_may_still_strengthen(self) -> None:
        """The asymmetry is the point: strengthening calls ARE present."""
        found = symbols("_recovery.py")
        assert "disable_vt_switching" in found
        assert "grab_set_global" in found

    def test_surfaces_never_touches_grab_or_vt(self) -> None:
        """Window ownership and lock strength stay separate concerns."""
        banned = {"grab_release", "grab_set", "grab_set_global", "restore_vt_switching"}
        assert symbols("_surfaces.py") & banned == set()

    def test_detect_thread_never_touches_tk(self) -> None:
        """Tk is not thread-safe; the RandR thread may only queue."""
        source = (SOURCE_ROOT / "_detect.py").read_text(encoding="utf-8")
        loop_body = source.split("def _loop(")[1].split("def ")[0]
        assert "self._sink.put" in loop_body
        for forbidden in ("geometry(", "deiconify(", "lift(", "grab_"):
            assert forbidden not in loop_body


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
        config = LockConfig(mode="soft")
        surfaces = SurfaceSet(mock_root, config, MagicMock())
        enumerator = MagicMock()
        enumerator.scan.return_value = BOTH
        recovery = RecoveryLoop(
            mock_root,
            RecoveryCollaborators(
                config=config,
                surfaces=surfaces,
                enumerator=enumerator,
                detector=MagicMock(),
                hooks=MagicMock(),
            ),
        )
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
        config = LockConfig(mode="soft")
        surfaces = SurfaceSet(mock_root, config, MagicMock())
        enumerator = MagicMock()
        enumerator.scan.return_value = BOTH
        recovery = RecoveryLoop(
            mock_root,
            RecoveryCollaborators(
                config=config,
                surfaces=surfaces,
                enumerator=enumerator,
                detector=MagicMock(),
                hooks=MagicMock(),
            ),
        )
        assert all(not recovery.tick().vt_reasserted for _ in range(31))


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
