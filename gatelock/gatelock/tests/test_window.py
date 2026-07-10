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
            "gatelock._window.disable_vt_switching", return_value=True
        ) as mock_disable:
            window.setup()

        mock_root.overrideredirect.assert_called_once_with(boolean=True)
        mock_root.attributes.assert_any_call(fullscreen=True)
        mock_root.attributes.assert_any_call(topmost=True)
        mock_disable.assert_called_once()
        assert window._vt_disabled is True

    def test_soft_mode_skips_overrideredirect_and_vt(
        self, mock_root: MagicMock
    ) -> None:
        """Soft mode never calls overrideredirect or disables VT switching."""
        window, _hooks = make_window(mock_root, config=LockConfig(mode="soft"))

        with patch("gatelock._window.disable_vt_switching") as mock_disable:
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

        mock_root.configure.assert_called_once_with(bg="#000000", cursor="arrow")


class TestGrabInput:
    """Tests for LockWindow.grab_input."""

    def test_global_grab_dispatches_to_acquire(self, mock_root: MagicMock) -> None:
        """grab="global" triggers the retry-aware acquisition path."""
        window, _hooks = make_window(
            mock_root, config=LockConfig(mode="soft", grab="global")
        )

        with patch.object(window, "_acquire_global_grab") as mock_acquire:
            window.grab_input()

        mock_acquire.assert_called_once_with(attempt=1)
        mock_root.after.assert_called_once_with(100, window._notify_focus_ready)

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


class TestAcquireGlobalGrab:
    """Tests for LockWindow._acquire_global_grab."""

    def test_success_focuses_and_notifies(self, mock_root: MagicMock) -> None:
        """A successful grab forces focus and notifies the hook."""
        window, hooks = make_window(mock_root, config=LockConfig(mode="hard"))

        window._acquire_global_grab(attempt=1)

        mock_root.grab_set_global.assert_called_once_with()
        mock_root.focus_force.assert_called_once_with()
        hooks.on_focus_ready.assert_called_once_with()

    def test_success_swallows_tclerror_from_focus(self, mock_root: MagicMock) -> None:
        """A TclError while focusing after a successful grab is swallowed."""
        mock_root.focus_force.side_effect = tk.TclError("gone")
        window, hooks = make_window(mock_root, config=LockConfig(mode="hard"))

        window._acquire_global_grab(attempt=1)  # must not raise

        hooks.on_focus_ready.assert_not_called()

    def test_failure_with_retry_zero_falls_back_to_local(
        self, mock_root: MagicMock
    ) -> None:
        """grab_retry_ms=0 falls back to a local grab on the first failure."""
        mock_root.grab_set_global.side_effect = tk.TclError("held by another client")
        window, _hooks = make_window(
            mock_root, config=LockConfig(mode="hard", grab_retry_ms=0)
        )

        window._acquire_global_grab(attempt=1)

        mock_root.grab_set.assert_called_once_with()
        mock_root.after.assert_not_called()

    def test_failure_with_retry_zero_swallows_local_grab_tclerror(
        self, mock_root: MagicMock
    ) -> None:
        """The local-grab fallback itself swallows a TclError too."""
        mock_root.grab_set_global.side_effect = tk.TclError("held")
        mock_root.grab_set.side_effect = tk.TclError("also gone")
        window, _hooks = make_window(
            mock_root, config=LockConfig(mode="hard", grab_retry_ms=0)
        )

        window._acquire_global_grab(attempt=1)  # must not raise

    def test_failure_with_default_retry_schedules_retry(
        self, mock_root: MagicMock
    ) -> None:
        """Default (None) retry interval reschedules every 200ms, logging every 25th."""
        mock_root.grab_set_global.side_effect = tk.TclError("held")
        window, _hooks = make_window(mock_root, config=LockConfig(mode="hard"))

        window._acquire_global_grab(attempt=24)

        assert mock_root.after.call_count == 1
        scheduled_delay = mock_root.after.call_args[0][0]
        assert scheduled_delay == 200

    def test_failure_logs_every_grab_log_every_attempts(
        self, mock_root: MagicMock
    ) -> None:
        """A warning is logged only when attempt is a multiple of grab_log_every."""
        mock_root.grab_set_global.side_effect = tk.TclError("held")
        window, _hooks = make_window(
            mock_root, config=LockConfig(mode="hard", grab_log_every=5)
        )

        with patch("gatelock._window._logger") as mock_logger:
            window._acquire_global_grab(attempt=5)
            mock_logger.warning.assert_called_once()

        with patch("gatelock._window._logger") as mock_logger:
            window._acquire_global_grab(attempt=3)
            mock_logger.warning.assert_not_called()

    def test_failure_with_custom_retry_ms_uses_it(self, mock_root: MagicMock) -> None:
        """An explicit positive grab_retry_ms is used as the reschedule delay."""
        mock_root.grab_set_global.side_effect = tk.TclError("held")
        window, _hooks = make_window(
            mock_root, config=LockConfig(mode="hard", grab_retry_ms=50)
        )

        window._acquire_global_grab(attempt=1)

        scheduled_delay = mock_root.after.call_args[0][0]
        assert scheduled_delay == 50

    def test_rescheduled_callback_increments_attempt(
        self, mock_root: MagicMock
    ) -> None:
        """The rescheduled callback re-invokes with attempt + 1."""
        mock_root.grab_set_global.side_effect = tk.TclError("held")
        window, _hooks = make_window(mock_root, config=LockConfig(mode="hard"))

        window._acquire_global_grab(attempt=1)
        scheduled_callback = mock_root.after.call_args[0][1]

        with patch.object(window, "_acquire_global_grab") as mock_acquire:
            scheduled_callback()

        mock_acquire.assert_called_once_with(attempt=2)


class TestNotifyFocusReady:
    """Tests for LockWindow._notify_focus_ready."""

    def test_calls_hook(self, mock_root: MagicMock) -> None:
        """The on_focus_ready hook is invoked."""
        window, hooks = make_window(mock_root)

        window._notify_focus_ready()

        hooks.on_focus_ready.assert_called_once_with()

    def test_swallows_tclerror_from_hook(self, mock_root: MagicMock) -> None:
        """A TclError raised by the hook (widget already destroyed) is swallowed."""
        hooks = MagicMock()
        hooks.on_focus_ready.side_effect = tk.TclError("destroyed")
        window, _hooks = make_window(mock_root, hooks=hooks)

        window._notify_focus_ready()  # must not raise
