"""Tests for the shared safety guards."""

from __future__ import annotations

import sys
import tkinter as tk
from unittest.mock import MagicMock, patch

import pytest

from gatelock._guards import (
    _probe_x_server,
    assert_not_under_pytest,
    wait_for_x_server,
)


class TestAssertNotUnderPytest:
    """Refuse to build a real grabbing window inside a test run."""

    def test_raises_under_pytest_with_real_tkinter(self) -> None:
        """The dangerous combination is rejected."""
        with pytest.raises(RuntimeError, match="refusing to build"):
            assert_not_under_pytest("the workout lock")

    def test_allows_when_tkinter_is_mocked(self) -> None:
        """A properly isolated test cannot open a window, so it is allowed."""
        fake_tk = MagicMock()
        fake_tk.__name__ = "MagicMock"
        with patch("gatelock._guards.tk", fake_tk):
            assert_not_under_pytest("the workout lock")

    def test_allows_outside_pytest(self) -> None:
        """In production there is no pytest, so nothing is blocked."""
        modules = {k: v for k, v in sys.modules.items() if k != "pytest"}
        with patch.dict("sys.modules", modules, clear=True):
            assert_not_under_pytest("the workout lock")


class TestWaitForXServer:
    """Gate on an X server existing -- never on how many outputs are live."""

    def test_returns_true_immediately(self) -> None:
        """A ready display returns at once."""
        assert wait_for_x_server(probe=lambda: True) is True

    def test_retries_then_succeeds(self) -> None:
        """A slow display is waited for."""
        results = iter([False, False, True])
        sleeps: list[float] = []
        assert (
            wait_for_x_server(
                probe=lambda: next(results),
                sleep=sleeps.append,
                monotonic=lambda: 0.0,
            )
            is True
        )
        assert sleeps == [1.0, 1.0]

    def test_times_out(self) -> None:
        """A display that never arrives gives up and says so."""
        clock = iter([0.0, 100.0])
        assert (
            wait_for_x_server(
                probe=lambda: False,
                sleep=lambda _s: None,
                monotonic=lambda: next(clock),
                timeout_s=1.0,
            )
            is False
        )

    def test_zero_live_outputs_does_not_block_arming(self) -> None:
        """THE 2b rule: a connected X server with dark monitors still arms.

        This function must answer "is there an X server", nothing more. If it
        ever consulted output liveness, a dark monitor would once again mean
        "do not lock" instead of "lock without showing".
        """
        assert wait_for_x_server(probe=lambda: True) is True


class TestProbeXServer:
    """The default probe."""

    def test_success_destroys_the_probe_window(self) -> None:
        """A working display yields True and leaves nothing behind."""
        fake_root = MagicMock()
        with patch("gatelock._guards.tk.Tk", return_value=fake_root):
            assert _probe_x_server() is True
        fake_root.destroy.assert_called_once_with()

    def test_failure_returns_false(self) -> None:
        """No display yields False rather than raising."""
        with patch("gatelock._guards.tk.Tk", side_effect=tk.TclError("no display")):
            assert _probe_x_server() is False
