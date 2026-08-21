"""Tests for LockWindow's v0.2.0 behaviour: arming, holder naming, teardown."""

from __future__ import annotations

import queue
import signal
from unittest.mock import MagicMock, patch

from gatelock._arbiter import (
    RANK_DIET_GUARD,
    RANK_SCREEN_LOCKER,
    RANK_WAKE_ALARM,
    Claim,
)
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
        arbiter.claim = Claim(
            app="screen_locker",
            rank=RANK_SCREEN_LOCKER,
            pid=1,
            started="2026-07-25T12:49:40+00:00",
            grab="global",
            disable_vt=True,
            instance_id="ours",
        )
        arbiter.describe_holder.return_value = Claim(
            app="diet_guard",
            rank=RANK_DIET_GUARD,
            pid=3353,
            started="2026-07-25T12:49:40+00:00",
            grab="global",
            disable_vt=True,
            instance_id="t",
        )
        window, _hooks = make_window(
            mock_root, config=LockConfig(mode="hard", preempt_weaker_holder=False)
        )
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


class TestPreemptWeakerHolder:
    """A weaker incumbent must not block a stronger claim indefinitely."""

    def _arbiter_with(
        self, *, our_rank: int, holder_rank: int, holder_pid: int
    ) -> MagicMock:
        arbiter = MagicMock()
        arbiter.claim = Claim(
            app="ours",
            rank=our_rank,
            pid=1,
            started="2026-08-21T12:00:00+00:00",
            grab="global",
            disable_vt=True,
            instance_id="ours",
        )
        arbiter.describe_holder.return_value = Claim(
            app="holder",
            rank=holder_rank,
            pid=holder_pid,
            started="2026-08-21T07:04:07+00:00",
            grab="global",
            disable_vt=True,
            instance_id="theirs",
        )
        return arbiter

    def test_signals_a_weaker_holder(self, mock_root: MagicMock) -> None:
        arbiter = self._arbiter_with(
            our_rank=RANK_SCREEN_LOCKER, holder_rank=RANK_DIET_GUARD, holder_pid=4075
        )
        window, _hooks = make_window(mock_root, config=LockConfig(mode="hard", preempt_weaker_holder=True))
        window._arbiter = arbiter
        with patch("gatelock._window.os.kill") as kill:
            window._log_grab_blocked(25)
        kill.assert_called_once_with(4075, signal.SIGTERM)

    def test_never_signals_a_stronger_holder(self, mock_root: MagicMock) -> None:
        arbiter = self._arbiter_with(
            our_rank=RANK_DIET_GUARD, holder_rank=RANK_SCREEN_LOCKER, holder_pid=4137
        )
        window, _hooks = make_window(mock_root, config=LockConfig(mode="hard", preempt_weaker_holder=True))
        window._arbiter = arbiter
        with patch("gatelock._window.os.kill") as kill:
            window._log_grab_blocked(25)
        kill.assert_not_called()

    def test_signals_the_same_holder_only_once(self, mock_root: MagicMock) -> None:
        arbiter = self._arbiter_with(
            our_rank=RANK_SCREEN_LOCKER, holder_rank=RANK_DIET_GUARD, holder_pid=4075
        )
        window, _hooks = make_window(mock_root, config=LockConfig(mode="hard", preempt_weaker_holder=True))
        window._arbiter = arbiter
        with patch("gatelock._window.os.kill") as kill:
            window._log_grab_blocked(25)
            window._log_grab_blocked(50)
        kill.assert_called_once_with(4075, signal.SIGTERM)

    def test_disabled_by_config(self, mock_root: MagicMock) -> None:
        arbiter = self._arbiter_with(
            our_rank=RANK_SCREEN_LOCKER, holder_rank=RANK_DIET_GUARD, holder_pid=4075
        )
        window, _hooks = make_window(
            mock_root, config=LockConfig(mode="hard", preempt_weaker_holder=False)
        )
        window._arbiter = arbiter
        with patch("gatelock._window.os.kill") as kill:
            window._log_grab_blocked(25)
        kill.assert_not_called()

    def test_off_by_default(self, mock_root: MagicMock) -> None:
        """Preemption is opt-in, so no app can evict anyone by accident.

        wake_alarm outranks screen_locker and builds a plain hard LockConfig.
        While the default was True, that combination SIGTERMed the *armed
        workout lock*, unlocking enforcement with no workout logged.
        """
        arbiter = self._arbiter_with(
            our_rank=RANK_WAKE_ALARM,
            holder_rank=RANK_SCREEN_LOCKER,
            holder_pid=4137,
        )
        window, _hooks = make_window(mock_root, config=LockConfig(mode="hard"))
        window._arbiter = arbiter
        with patch("gatelock._window.os.kill") as kill:
            window._log_grab_blocked(25)
        kill.assert_not_called()

    def test_no_arbiter_means_no_preemption(self, mock_root: MagicMock) -> None:
        window, _hooks = make_window(mock_root, config=LockConfig(mode="hard", preempt_weaker_holder=True))
        with patch("gatelock._window.os.kill") as kill:
            window._maybe_preempt(
                Claim(
                    app="holder",
                    rank=RANK_DIET_GUARD,
                    pid=4075,
                    started="2026-08-21T07:04:07+00:00",
                    grab="global",
                    disable_vt=True,
                    instance_id="theirs",
                )
            )
        kill.assert_not_called()

    def test_a_holder_that_is_already_gone_is_reported_at_info(
        self, mock_root: MagicMock
    ) -> None:
        arbiter = self._arbiter_with(
            our_rank=RANK_SCREEN_LOCKER, holder_rank=RANK_DIET_GUARD, holder_pid=4075
        )
        window, _hooks = make_window(mock_root, config=LockConfig(mode="hard", preempt_weaker_holder=True))
        window._arbiter = arbiter
        with (
            patch("gatelock._window.os.kill", side_effect=ProcessLookupError),
            patch("gatelock._window._logger") as logger,
        ):
            window._log_grab_blocked(25)
        assert logger.info.called

    def test_an_unsignalable_holder_is_reported_not_raised(
        self, mock_root: MagicMock
    ) -> None:
        arbiter = self._arbiter_with(
            our_rank=RANK_SCREEN_LOCKER, holder_rank=RANK_DIET_GUARD, holder_pid=4075
        )
        window, _hooks = make_window(mock_root, config=LockConfig(mode="hard", preempt_weaker_holder=True))
        window._arbiter = arbiter
        with (
            patch("gatelock._window.os.kill", side_effect=OSError("nope")),
            patch("gatelock._window._logger") as logger,
        ):
            window._log_grab_blocked(25)
        assert logger.exception.called


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
