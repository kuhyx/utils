"""Tests for LockWindow's v0.2.0 behaviour: arming, holder naming, teardown."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from gatelock._arbiter import (
    RANK_DIET_GUARD,
    RANK_SCREEN_LOCKER,
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
        with patch("gatelock._preempt._logger") as logger:
            window._log_grab_blocked(25)
        assert "diet_guard" in str(logger.warning.call_args)

    def test_falls_back_when_no_gatelock_app_holds_it(
        self, mock_root: MagicMock
    ) -> None:
        """With no gatelock holder, a foreign X client is the honest guess."""
        window, _hooks = make_window(mock_root, config=LockConfig(mode="hard"))
        with patch("gatelock._preempt._logger") as logger:
            window._log_grab_blocked(25)
        assert "fullscreen game" in str(logger.warning.call_args)

    def test_arbiter_without_holder(self, mock_root: MagicMock) -> None:
        """An arbiter that reports no holder takes the same path."""
        arbiter = MagicMock()
        arbiter.describe_holder.return_value = None
        window, _hooks = make_window(mock_root, config=LockConfig(mode="hard"))
        window._arbiter = arbiter
        with patch("gatelock._preempt._logger") as logger:
            window._log_grab_blocked(50)
        assert "fullscreen game" in str(logger.warning.call_args)
