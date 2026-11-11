# Copyright (c) 2026 Krzysztof Rudnicki
"""Tests for a weaker armed lock stepping back for a stronger one.

The trigger is the whole safety argument, so most tests are about what must NOT
trigger it: equal rank, lower rank, a dead claim, a stronger-ranked app that
locks more weakly, a loop the app stopped on purpose. See ``_stepback.py``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from gatelock._arbiter import RANK_DIET_GUARD, RANK_SCREEN_LOCKER
from gatelock._config import LockConfig
from gatelock._window import LockWindow
from gatelock.tests.conftest import make_arbiter

if TYPE_CHECKING:
    from pathlib import Path

    from gatelock._arbiter import Arbiter

RANK_MID = 150


def _tick(window: LockWindow) -> None:
    window._stepback._tick()


class TestTrigger:
    """Only a strictly stronger, live, at-least-as-firm claim makes it step back."""

    def test_stronger_live_claim_suspends(
        self,
        armed: tuple[LockWindow, Arbiter],
        mock_root: MagicMock,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Hide, release the grab, drop the holder; the claim stays published."""
        window, arbiter = armed
        strong = make_arbiter(tmp_path, "screen_locker", RANK_SCREEN_LOCKER)
        windows = [s.window for s in window.surfaces._surfaces.values()]
        with caplog.at_level(logging.WARNING):
            _tick(window)
        assert window._stepback.suspended
        assert "steps back" in caplog.text
        assert "screen_locker" in caplog.text
        mock_root.grab_release.assert_called_once_with()
        mock_root.withdraw.assert_called_once_with()
        assert windows
        assert all(w.withdraw.called for w in windows)
        assert not window.recovery.running
        assert not arbiter.holds_screen
        assert arbiter.claim.grab_held is False
        assert arbiter.claim.instance_id in {
            c.instance_id for c in strong.live_claims()
        }
        strong.release()

    @pytest.mark.parametrize(
        ("app", "rank"),
        [("twin", RANK_MID), ("diet_guard", RANK_DIET_GUARD)],
    )
    def test_equal_or_lower_rank_never_does(
        self, armed: tuple[LockWindow, Arbiter], tmp_path: Path, app: str, rank: int
    ) -> None:
        """Rank must be strictly higher."""
        window, _ = armed
        other = make_arbiter(tmp_path, app, rank)
        _tick(window)
        assert not window._stepback.suspended
        other.release()

    def test_dead_claim_never_does(
        self, armed: tuple[LockWindow, Arbiter], tmp_path: Path
    ) -> None:
        """A stale claim file (its owner died, flock gone) is no reason."""
        window, _ = armed
        ghost = make_arbiter(tmp_path, "screen_locker", RANK_SCREEN_LOCKER)
        assert ghost._claim_handle is not None
        ghost._claim_handle.close()  # the kernel's view of a dead owner
        _tick(window)
        assert not window._stepback.suspended

    def test_a_weaker_locking_app_never_does(
        self, armed: tuple[LockWindow, Arbiter], tmp_path: Path
    ) -> None:
        """Rank must never weaken the lock: no grab, no VT -> no step back."""
        window, _ = armed
        soft = make_arbiter(
            tmp_path, "alarm", RANK_SCREEN_LOCKER, grab="none", vt=False
        )
        _tick(window)
        assert not window._stepback.suspended
        soft.release()

    def test_a_loop_the_app_stopped_is_left_alone(
        self, armed: tuple[LockWindow, Arbiter], tmp_path: Path
    ) -> None:
        """Study mode stops recovery on purpose; that is not ours to suspend."""
        window, _ = armed
        window.recovery.stop()
        strong = make_arbiter(tmp_path, "screen_locker", RANK_SCREEN_LOCKER)
        _tick(window)
        assert not window._stepback.suspended
        strong.release()

    def test_without_an_arbiter_it_is_inert(self, mock_root: MagicMock) -> None:
        """No arbitration, nothing to step back for."""
        window = LockWindow(mock_root, LockConfig(mode="hard"), MagicMock())
        window.setup()
        window.grab_input()
        mock_root.after.reset_mock()
        window._stepback.start()
        assert window._stepback._job is None
