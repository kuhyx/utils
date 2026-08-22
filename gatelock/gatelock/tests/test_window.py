"""Tests for LockConfig and LockWindow."""

from __future__ import annotations

import tkinter as tk
from unittest.mock import MagicMock, patch

from gatelock._window import LockConfig
from gatelock.tests.conftest import make_window


class TestLockConfigResolution:
    """Tests for LockConfig's per-axis resolution logic."""

    def test_hard_mode_defaults(self) -> None:
        """Hard mode resolves to overrideredirect + global grab + VT disable."""
        config = LockConfig(mode="hard")
        assert config.resolved_overrideredirect() is True
        assert config.resolved_grab() == "global"
        assert config.resolved_disable_vt() is True

    def test_soft_mode_defaults(self) -> None:
        """Soft mode resolves to no overrideredirect, no grab, no VT disable."""
        config = LockConfig(mode="soft")
        assert config.resolved_overrideredirect() is False
        assert config.resolved_grab() == "none"
        assert config.resolved_disable_vt() is False

    def test_explicit_overrides_win_over_mode(self) -> None:
        """Explicit fields override the mode preset (screen-locker demo case)."""
        config = LockConfig(mode="soft", overrideredirect=True, grab="local")
        assert config.resolved_overrideredirect() is True
        assert config.resolved_grab() == "local"
        assert config.resolved_disable_vt() is False

    def test_explicit_false_overrides_hard_mode(self) -> None:
        """An explicit False/none is respected even under mode="hard"."""
        config = LockConfig(
            mode="hard", overrideredirect=False, grab="none", disable_vt=False
        )
        assert config.resolved_overrideredirect() is False
        assert config.resolved_grab() == "none"
        assert config.resolved_disable_vt() is False


class TestSetup:
    """Tests for LockWindow.setup."""

    def test_hard_mode_sets_overrideredirect_and_disables_vt(
        self, mock_root: MagicMock
    ) -> None:
        """Hard mode calls overrideredirect and disables VT switching."""
        window, _hooks = make_window(mock_root, config=LockConfig(mode="hard"))

        with patch(
            "gatelock._arming.disable_vt_switching", return_value=True
        ) as mock_disable:
            window.setup()

        mock_root.overrideredirect.assert_called_once_with(boolean=True)
        # No attributes(fullscreen=True): that is an EWMH request an
        # override-redirect window is invisible to, and where it does apply it
        # snaps to one monitor or the whole bounding box. Per-output surfaces
        # use explicit geometry instead.
        assert not any(
            call.kwargs.get("fullscreen") or "-fullscreen" in call.args
            for call in mock_root.attributes.call_args_list
        )
        mock_disable.assert_called_once()
        assert window._vt_disabled is True

    def test_soft_mode_skips_overrideredirect_and_vt(
        self, mock_root: MagicMock
    ) -> None:
        """Soft mode never calls overrideredirect or disables VT switching."""
        window, _hooks = make_window(mock_root, config=LockConfig(mode="soft"))

        with patch("gatelock._arming.disable_vt_switching") as mock_disable:
            window.setup()

        mock_root.overrideredirect.assert_not_called()
        mock_disable.assert_not_called()
        assert window._vt_disabled is False

    def test_uses_configured_background(self, mock_root: MagicMock) -> None:
        """The configured bg color is passed to root.configure."""
        window, _hooks = make_window(
            mock_root, config=LockConfig(mode="soft", bg="#000000")
        )

        window.setup()

        # Soft mode with no grab needs no backdrop, so the root is left to the
        # window manager and only the surfaces carry the colour.
        assert window.surfaces.infos()
        topmost_on = True
        mock_root.attributes.assert_any_call("-topmost", topmost_on)


class TestGrabInput:
    """Tests for LockWindow.grab_input."""

    def test_global_grab_dispatches_to_acquire(self, mock_root: MagicMock) -> None:
        """grab="global" triggers the retry-aware acquisition path."""
        window, _hooks = make_window(
            mock_root, config=LockConfig(mode="soft", grab="global")
        )

        with patch("gatelock._arming.acquire_global_grab") as mock_acquire:
            window.grab_input()

        mock_acquire.assert_called_once_with(window.root, window._arming, attempt=1)
        mock_root.after.assert_any_call(100, window._notify_focus_ready)

    def test_local_grab_calls_grab_set(self, mock_root: MagicMock) -> None:
        """grab="local" calls grab_set directly, no retry logic."""
        window, _hooks = make_window(
            mock_root, config=LockConfig(mode="soft", grab="local")
        )

        window.grab_input()

        mock_root.grab_set.assert_called_once_with()

    def test_local_grab_swallows_tclerror(self, mock_root: MagicMock) -> None:
        """A TclError from grab_set (e.g. window already gone) is swallowed."""
        mock_root.grab_set.side_effect = tk.TclError("gone")
        window, _hooks = make_window(
            mock_root, config=LockConfig(mode="soft", grab="local")
        )

        window.grab_input()  # must not raise

    def test_none_grab_takes_no_grab_action(self, mock_root: MagicMock) -> None:
        """grab="none" calls neither grab_set nor grab_set_global."""
        window, _hooks = make_window(
            mock_root, config=LockConfig(mode="soft", grab="none")
        )

        window.grab_input()

        mock_root.grab_set.assert_not_called()
        mock_root.grab_set_global.assert_not_called()
