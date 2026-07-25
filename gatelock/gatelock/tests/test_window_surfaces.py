"""Tests for LockWindow's v0.2.0 behaviour: arming, holder naming, teardown."""

from __future__ import annotations

import queue
from unittest.mock import MagicMock, patch

from gatelock._arbiter import RANK_DIET_GUARD, Claim
from gatelock._detect import _RandrEventSource
from gatelock._outputs import Output, OutputRect
from gatelock._window import LockConfig
from gatelock.tests.conftest import make_window

# Captured before the autouse hermetic fixture replaces it.
REAL_RANDR_START = _RandrEventSource.start

DARK_ONLY = (Output("DP-0", connected=True, rect=None, primary=True),)
TWO_LIVE = (
    Output("DP-0", connected=True, rect=OutputRect(0, 0, 3840, 2160), primary=True),
    Output("HDMI-0", connected=True, rect=OutputRect(3840, 0, 2560, 1440)),
)


class TestArmWithoutDisplay:
    """Output count must never gate arming."""

    def test_zero_live_outputs_still_arms(self, mock_root: MagicMock) -> None:
        """The 2b rule: dark monitors mean lock silently, not decline to lock."""
        window, _hooks = make_window(mock_root, config=LockConfig(mode="hard"))
        with patch("gatelock._outputs.scan_xrandr", return_value=DARK_ONLY):
            window.setup()
        assert window.surfaces.names() == frozenset()
        # Armed regardless: VT was disabled and the backdrop is up.
        assert window._vt_disabled is True
        mock_root.overrideredirect.assert_called_once_with(boolean=True)

    def test_reports_outputs_live_but_uncovered(self, mock_root: MagicMock) -> None:
        """A live output with no surface is an error at startup, not silence."""
        window, _hooks = make_window(mock_root, config=LockConfig(mode="hard"))
        with (
            patch("gatelock._outputs.scan_xrandr", return_value=TWO_LIVE),
            patch(
                "gatelock._surfaces.SurfaceSet.verify",
                return_value=("HDMI-0",),
            ),
        ):
            window.setup()  # must log, not raise

    def test_builds_one_surface_per_live_output(self, mock_root: MagicMock) -> None:
        """Two live monitors means two surfaces, each at its own rectangle."""
        window, hooks = make_window(mock_root, config=LockConfig(mode="hard"))
        with patch("gatelock._outputs.scan_xrandr", return_value=TWO_LIVE):
            window.setup()
        assert sorted(window.surfaces.names()) == ["DP-0", "HDMI-0"]
        assert hooks.build_surface.call_count == 2


class TestGrabBlockedLogging:
    """Naming the real holder instead of blaming a fullscreen game."""

    def test_names_the_holding_gatelock_app(self, mock_root: MagicMock) -> None:
        """The 2026-07-25 diagnosis, available immediately."""
        arbiter = MagicMock()
        arbiter.describe_holder.return_value = Claim(
            app="diet_guard",
            rank=RANK_DIET_GUARD,
            pid=3353,
            started="2026-07-25T12:49:40+00:00",
            grab="global",
            disable_vt=True,
            instance_id="t",
        )
        window, _hooks = make_window(mock_root, config=LockConfig(mode="hard"))
        window._arbiter = arbiter
        with patch("gatelock._window._logger") as logger:
            window._log_grab_blocked(25)
        assert "diet_guard" in str(logger.warning.call_args)

    def test_falls_back_when_no_gatelock_app_holds_it(
        self, mock_root: MagicMock
    ) -> None:
        """With no gatelock holder, a foreign X client is the honest guess."""
        window, _hooks = make_window(mock_root, config=LockConfig(mode="hard"))
        with patch("gatelock._window._logger") as logger:
            window._log_grab_blocked(25)
        assert "fullscreen game" in str(logger.warning.call_args)

    def test_arbiter_without_holder(self, mock_root: MagicMock) -> None:
        """An arbiter that reports no holder takes the same path."""
        arbiter = MagicMock()
        arbiter.describe_holder.return_value = None
        window, _hooks = make_window(mock_root, config=LockConfig(mode="hard"))
        window._arbiter = arbiter
        with patch("gatelock._window._logger") as logger:
            window._log_grab_blocked(50)
        assert "fullscreen game" in str(logger.warning.call_args)


class TestFocusNotifiedOnce:
    """Both call sites are load-bearing, so the guard is on the callee."""

    def test_second_notification_is_suppressed(self, mock_root: MagicMock) -> None:
        """The hook fires once even though two timings can reach it."""
        window, hooks = make_window(mock_root, config=LockConfig(mode="hard"))
        window._notify_focus_ready()
        window._notify_focus_ready()
        hooks.on_focus_ready.assert_called_once()


class TestCloseReleasesTheScreen:
    """A clean exit must hand the screen to the next app."""

    def test_arbiter_is_released(self, mock_root: MagicMock) -> None:
        """Without this the alarm -> workout handoff strands the workout lock."""
        arbiter = MagicMock()
        window, _hooks = make_window(mock_root, config=LockConfig(mode="hard"))
        window._arbiter = arbiter
        window.close()
        arbiter.release.assert_called_once_with()

    def test_close_without_arbiter(self, mock_root: MagicMock) -> None:
        """An unarbitrated lock still closes cleanly."""
        window, hooks = make_window(mock_root, config=LockConfig(mode="hard"))
        window.close()
        hooks.on_close.assert_called_once_with()


class TestRemainingBranches:
    """Small paths the other suites do not reach."""

    def test_claim_read_oserror(self, tmp_path: object) -> None:
        """A claim whose contents cannot be read is treated as absent."""
        from gatelock._arbiter import Arbiter

        arbiter = Arbiter("a", RANK_DIET_GUARD, grab="none", disable_vt=False)
        arbiter.publish()
        handle = MagicMock()
        handle.__enter__.return_value = handle
        handle.read.side_effect = OSError("io error")
        with (
            patch("gatelock._arbiter.Path.open", return_value=handle),
            patch("gatelock._arbiter._try_lock", return_value=False),
        ):
            assert arbiter.live_claims() == ()
        arbiter.release()

    def test_randr_start_spawns_thread(self) -> None:
        """A successful connect starts the watcher thread."""
        source = _RandrEventSource(queue.Queue())
        with (
            patch.object(source, "_connect", return_value=True),
            patch("gatelock._detect.threading.Thread") as thread_cls,
        ):
            assert REAL_RANDR_START(source) is True
        thread_cls.return_value.start.assert_called_once_with()

    def test_randr_loop_ignores_empty_batch(self) -> None:
        """A readable socket with no events posts no notice."""
        sink: queue.Queue[str] = queue.Queue()
        source = _RandrEventSource(sink)
        source._display = MagicMock()
        source._display.pending_events.return_value = 0
        calls = {"n": 0}

        def is_set() -> bool:
            calls["n"] += 1
            return calls["n"] > 1

        source._stop = MagicMock()
        source._stop.is_set.side_effect = is_set
        with patch("gatelock._detect.select.select", return_value=([1], [], [])):
            source._loop()
        assert sink.empty()
