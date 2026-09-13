# Copyright (c) 2026 Krzysztof Rudnicki
"""Tests for the shared safety guards."""

from __future__ import annotations

import logging
import sys
import tkinter as tk
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from gatelock._guards import (
    X_WAIT_HEARTBEAT_S,
    _probe_x_server,
    assert_not_under_pytest,
    wait_for_x_server,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


class FakeClock:
    """A monotonic clock that only moves when something sleeps."""

    def __init__(self) -> None:
        self.value = 0.0
        self.slept: list[float] = []

    def now(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.value += seconds


def _false_then_true(after: int) -> Iterator[bool]:
    for _ in range(after):
        yield False
    while True:
        yield True


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

    def test_an_explicit_timeout_gives_up_and_says_so(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Opt-in only: a caller that asks for a bound gets one."""
        clock = FakeClock()
        with caplog.at_level(logging.ERROR):
            assert (
                wait_for_x_server(
                    probe=lambda: False,
                    sleep=clock.sleep,
                    monotonic=clock.now,
                    timeout_s=2.5,
                )
                is False
            )
        assert clock.slept == [1.0, 1.0, 1.0]
        assert "cannot build a lock window" in caplog.text

    def test_the_default_wait_outlives_the_old_sixty_second_deadline(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The 2026-09-13 rule: time never gates arming. A server that takes
        ten minutes to appear is still waited for, and the wait says so."""
        clock = FakeClock()
        probe = _false_then_true(after=600)
        with caplog.at_level(logging.WARNING):
            assert (
                wait_for_x_server(
                    probe=lambda: next(probe),
                    sleep=clock.sleep,
                    monotonic=clock.now,
                )
                is True
            )
        assert len(clock.slept) == 600
        assert "X server answered after 600s; arming now" in caplog.text

    def test_a_long_wait_heartbeats_at_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A silent wait looks like a hung unit; it must re-state itself."""
        clock = FakeClock()
        probe = _false_then_true(after=int(X_WAIT_HEARTBEAT_S * 2) + 1)
        with caplog.at_level(logging.WARNING):
            wait_for_x_server(
                probe=lambda: next(probe), sleep=clock.sleep, monotonic=clock.now
            )
        heartbeats = [r for r in caplog.records if "still waiting" in r.message]
        assert len(heartbeats) == 2
        assert all(r.levelno == logging.WARNING for r in heartbeats)
        assert "nothing is locked" in heartbeats[0].message

    def test_a_heartbeat_skips_ahead_after_a_long_sleep(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """One coarse sleep past several heartbeat slots logs once, not once
        per missed slot, and the next heartbeat lands on a future slot."""
        clock = FakeClock()
        probe = _false_then_true(after=2)
        with caplog.at_level(logging.WARNING):
            wait_for_x_server(
                probe=lambda: next(probe),
                sleep=clock.sleep,
                monotonic=clock.now,
                interval_s=X_WAIT_HEARTBEAT_S * 3,
            )
        assert sum("still waiting" in r.message for r in caplog.records) == 1

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
