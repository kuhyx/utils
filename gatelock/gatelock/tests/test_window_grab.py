"""Tests for acquiring the global input grab and its retry loop.

Split from ``test_window.py`` to hold the shared 250-line cap.
"""


from __future__ import annotations

import tkinter as tk
from unittest.mock import MagicMock, patch

from gatelock._window import LockConfig
from gatelock.tests.conftest import make_window


class TestAcquireGlobalGrab:
    """Tests for LockWindow._acquire_global_grab."""

    def test_success_focuses_and_notifies(self, mock_root: MagicMock) -> None:
        """A successful grab forces focus and notifies the hook."""
        window, hooks = make_window(mock_root, config=LockConfig(mode="hard"))

        window._acquire_global_grab(attempt=1)

        mock_root.grab_set_global.assert_called_once_with()
        mock_root.focus_force.assert_called_once_with()
        hooks.on_focus_ready.assert_called_once_with(None)

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

        with patch("gatelock._preempt._logger") as mock_logger:
            window._acquire_global_grab(attempt=5)
            mock_logger.warning.assert_called_once()

        with patch("gatelock._preempt._logger") as mock_logger:
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

        with patch("gatelock._arming.acquire_global_grab") as mock_acquire:
            scheduled_callback()

        mock_acquire.assert_called_once_with(window.root, window._arming, attempt=2)


class TestNotifyFocusReady:
    """Tests for LockWindow._notify_focus_ready."""

    def test_calls_hook(self, mock_root: MagicMock) -> None:
        """The on_focus_ready hook is invoked."""
        window, hooks = make_window(mock_root)

        window._notify_focus_ready()

        hooks.on_focus_ready.assert_called_once_with(None)

    def test_swallows_tclerror_from_hook(self, mock_root: MagicMock) -> None:
        """A TclError raised by the hook (widget already destroyed) is swallowed."""
        hooks = MagicMock()
        hooks.on_focus_ready.side_effect = tk.TclError("destroyed")
        window, _hooks = make_window(mock_root, hooks=hooks)

        window._notify_focus_ready()  # must not raise
