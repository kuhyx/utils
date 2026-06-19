"""Tests for LockWindow signal handling, keepalive, close, and run lifecycle."""

from __future__ import annotations

import tkinter as tk
from unittest.mock import MagicMock, patch

import pytest

from gatelock.tests.conftest import make_window


class TestSignalLifecycle:
    """Tests for signal handler installation and dispatch."""

    def test_install_signal_handlers_registers_atexit_and_signals(
        self, mock_root: MagicMock
    ) -> None:
        """atexit and SIGTERM/SIGINT handlers are registered."""
        window, _hooks = make_window(mock_root)

        with (
            patch("gatelock._window.atexit.register") as mock_atexit,
            patch("gatelock._window.signal.signal") as mock_signal,
        ):
            window._install_signal_handlers()

        mock_atexit.assert_called_once_with(window._restore_vt)
        assert mock_signal.call_count == 2

    def test_install_signal_handlers_swallows_value_error(
        self, mock_root: MagicMock
    ) -> None:
        """A ValueError from signal.signal (e.g. not main thread) is swallowed."""
        window, _hooks = make_window(mock_root)

        with (
            patch("gatelock._window.atexit.register"),
            patch(
                "gatelock._window.signal.signal",
                side_effect=ValueError("not main thread"),
            ),
        ):
            window._install_signal_handlers()  # must not raise

    def test_on_signal_raises_system_exit(self, mock_root: MagicMock) -> None:
        """The signal handler raises SystemExit(0) to unwind run()'s finally."""
        window, _hooks = make_window(mock_root)

        with pytest.raises(SystemExit) as exc_info:
            window._on_signal(15, None)

        assert exc_info.value.code == 0


class TestKeepalive:
    """Tests for LockWindow._keepalive."""

    def test_reschedules_itself(self, mock_root: MagicMock) -> None:
        """Reschedules another keepalive tick via root.after."""
        window, _hooks = make_window(mock_root)

        window._keepalive()

        mock_root.after.assert_called_once_with(250, window._keepalive)

    def test_swallows_tclerror_when_window_gone(self, mock_root: MagicMock) -> None:
        """A TclError (window destroyed) from root.after is swallowed."""
        mock_root.after.side_effect = tk.TclError("destroyed")
        window, _hooks = make_window(mock_root)

        window._keepalive()  # must not raise


class TestRestoreVt:
    """Tests for LockWindow._restore_vt."""

    def test_restores_when_disabled(self, mock_root: MagicMock) -> None:
        """Calls restore_vt_switching and clears the flag when it was disabled."""
        window, _hooks = make_window(mock_root)
        window._vt_disabled = True

        with patch("gatelock._window.restore_vt_switching") as mock_restore:
            window._restore_vt()

        mock_restore.assert_called_once_with()
        assert window._vt_disabled is False

    def test_noop_when_never_disabled(self, mock_root: MagicMock) -> None:
        """Does nothing when VT switching was never disabled."""
        window, _hooks = make_window(mock_root)

        with patch("gatelock._window.restore_vt_switching") as mock_restore:
            window._restore_vt()

        mock_restore.assert_not_called()


class TestClose:
    """Tests for LockWindow.close."""

    def test_runs_teardown_restores_vt_and_destroys(self, mock_root: MagicMock) -> None:
        """A normal close runs the hook, restores VT, and destroys the root."""
        window, hooks = make_window(mock_root)
        window._vt_disabled = True

        with patch("gatelock._window.restore_vt_switching") as mock_restore:
            window.close()

        hooks.on_close.assert_called_once_with()
        mock_restore.assert_called_once_with()
        mock_root.destroy.assert_called_once_with()

    def test_idempotent_second_call_is_noop(self, mock_root: MagicMock) -> None:
        """Calling close() twice only runs teardown once."""
        window, hooks = make_window(mock_root)

        window.close()
        window.close()

        hooks.on_close.assert_called_once_with()
        mock_root.destroy.assert_called_once_with()

    def test_swallows_tclerror_from_destroy(self, mock_root: MagicMock) -> None:
        """A TclError from destroy() (already gone) is swallowed."""
        mock_root.destroy.side_effect = tk.TclError("already destroyed")
        window, _hooks = make_window(mock_root)

        window.close()  # must not raise


class TestRun:
    """Tests for LockWindow.run."""

    def test_runs_mainloop_then_closes(self, mock_root: MagicMock) -> None:
        """Installs signal handlers, keeps alive, runs mainloop, then closes."""
        window, hooks = make_window(mock_root)

        with (
            patch.object(window, "_install_signal_handlers") as mock_install,
            patch.object(window, "_keepalive") as mock_keepalive,
        ):
            window.run()

        mock_install.assert_called_once_with()
        mock_keepalive.assert_called_once_with()
        mock_root.mainloop.assert_called_once_with()
        hooks.on_close.assert_called_once_with()

    def test_closes_even_if_mainloop_raises(self, mock_root: MagicMock) -> None:
        """A SystemExit out of mainloop still runs close() via finally."""
        mock_root.mainloop.side_effect = SystemExit(0)
        window, hooks = make_window(mock_root)

        with (
            patch.object(window, "_install_signal_handlers"),
            patch.object(window, "_keepalive"),
        ):
            try:
                window.run()
            except SystemExit:
                pass
            else:
                msg = "expected SystemExit to propagate"
                raise AssertionError(msg)

        hooks.on_close.assert_called_once_with()
