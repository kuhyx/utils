# Copyright (c) 2026 Krzysztof Rudnicki
"""Re-arming after a step-back, and the failure paths around it.

Split from ``test_stepback.py`` (250-line cap); the ``armed`` fixture is in
``conftest.py``.
"""

from __future__ import annotations

import logging
import tkinter as tk
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from gatelock import _stepback
from gatelock._arbiter import RANK_SCREEN_LOCKER
from gatelock._config import GrabPolicy, LockConfig
from gatelock._window import LockWindow
from gatelock.tests.conftest import make_arbiter

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from gatelock._arbiter import Arbiter

RANK_MID = 150


def _tick(window: LockWindow) -> None:
    window._stepback._tick()


class TestRearm:
    """It comes back, fully, once nothing qualifying is live."""

    def _suspended(
        self, armed: tuple[LockWindow, Arbiter], tmp_path: Path
    ) -> tuple[LockWindow, Arbiter, Arbiter]:
        window, arbiter = armed
        strong = make_arbiter(tmp_path, "screen_locker", RANK_SCREEN_LOCKER)
        _tick(window)
        assert window._stepback.suspended
        return window, arbiter, strong

    def test_stays_hidden_while_the_stronger_is_live(
        self, armed: tuple[LockWindow, Arbiter], tmp_path: Path
    ) -> None:
        """Windowless until the stronger one is gone."""
        window, _, strong = self._suspended(armed, tmp_path)
        _tick(window)
        assert window._stepback.suspended
        strong.release()

    def test_rearms_fully_when_it_is_gone(
        self,
        armed: tuple[LockWindow, Arbiter],
        mock_root: MagicMock,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """VT, backdrop, surfaces, grab, holder and the loops all come back."""
        window, arbiter, strong = self._suspended(armed, tmp_path)
        strong.release()
        mock_root.grab_set_global.reset_mock()
        with (
            patch("gatelock._stepback.disable_vt_switching") as vt,
            caplog.at_level(logging.WARNING),
        ):
            _tick(window)
        assert not window._stepback.suspended
        assert "re-arms" in caplog.text
        vt.assert_called_once_with()
        mock_root.deiconify.assert_called_once_with()
        mock_root.grab_set_global.assert_called_once_with()
        assert arbiter.holds_screen
        assert window.recovery.running
        for surface in window.surfaces._surfaces.values():
            surface.window.deiconify.assert_called()

    def test_without_vt_policy_it_leaves_vt_alone(
        self, mock_root: MagicMock, tmp_path: Path
    ) -> None:
        """A lock that never disabled VT does not start now."""
        arbiter = make_arbiter(tmp_path, "leetcode_guard", RANK_MID, vt=False)
        grab = GrabPolicy(disable_vt=False)
        config = LockConfig(mode="hard", grab=grab, rank=RANK_MID)
        window = LockWindow(mock_root, config, MagicMock(), arbiter=arbiter)
        window.setup()
        window.grab_input()
        strong = make_arbiter(tmp_path, "screen_locker", RANK_SCREEN_LOCKER, vt=False)
        _tick(window)
        strong.release()
        with patch("gatelock._stepback.disable_vt_switching") as vt:
            _tick(window)
        assert not window._stepback.suspended
        vt.assert_not_called()
        window.close()

    def test_gives_up_waiting_after_the_deadline(
        self,
        armed: tuple[LockWindow, Arbiter],
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A stuck stronger claim cannot keep the machine unlocked forever."""
        window, _, strong = self._suspended(armed, tmp_path)
        step = window._stepback
        step._since = step._clock() - _stepback.QUEUE_DEADLINE_SECONDS - 1
        with caplog.at_level(logging.ERROR):
            _tick(window)
        assert not step.suspended
        assert "gave up" in caplog.text
        strong.release()


class TestRobustness:
    """A failing step must not leave the lock half-down."""

    def test_tk_errors_are_logged_and_the_rest_still_happens(
        self,
        armed: tuple[LockWindow, Arbiter],
        mock_root: MagicMock,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A failed grab release is logged; hiding and the claim still follow."""
        window, arbiter = armed
        mock_root.grab_release.side_effect = tk.TclError("no grab")
        strong = make_arbiter(tmp_path, "screen_locker", RANK_SCREEN_LOCKER)
        with caplog.at_level(logging.WARNING):
            _tick(window)
        assert "grab release failed" in caplog.text
        assert window._stepback.suspended
        assert not arbiter.holds_screen
        strong.release()

    def test_a_raise_does_not_end_the_checking(
        self, armed: tuple[LockWindow, Arbiter], caplog: pytest.LogCaptureFixture
    ) -> None:
        """The reschedule is in ``finally``; one bad check is just logged."""
        window, _ = armed
        with (
            patch("gatelock._stepback.outranking", side_effect=ValueError("boom")),
            caplog.at_level(logging.ERROR),
        ):
            _tick(window)
        assert "step-back check raised" in caplog.text
        assert window._stepback._job is not None

    def test_close_stops_the_checking(self, armed: tuple[LockWindow, Arbiter]) -> None:
        """No timer outlives the window."""
        window, _ = armed
        window.close()
        assert window._stepback._job is None

    def test_stop_survives_a_dead_root(
        self, armed: tuple[LockWindow, Arbiter], mock_root: MagicMock
    ) -> None:
        """Cancelling on a destroyed root is logged, not raised."""
        window, _ = armed
        mock_root.after_cancel.side_effect = tk.TclError("gone")
        window._stepback.stop()
        assert window._stepback._job is None
