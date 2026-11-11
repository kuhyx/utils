# Copyright (c) 2026 Krzysztof Rudnicki
"""Tests for the small pieces step-back is built from.

The startup grace in ``wait_for_turn``, ``Arbiter.drop_holder`` and
``SurfaceSet.set_visible``. The controller itself is in ``test_stepback.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, call, patch

from gatelock import RANK_DIET_GUARD, RANK_SCREEN_LOCKER, Arbiter
from gatelock._config import LockConfig
from gatelock._queue import STARTUP_GRACE_SECONDS, Timebase, wait_for_turn
from gatelock.tests.conftest import DP0, build_loop, make_arbiter

if TYPE_CHECKING:
    from pathlib import Path


class TestStartupGrace:
    """Simultaneous starters must see each other before anyone arms."""

    def test_the_real_constant_is_set(self) -> None:
        """Not zero in production (the test fixture zeroes the patched copy)."""
        assert STARTUP_GRACE_SECONDS == 1.5

    def test_waits_before_the_first_check_and_sees_a_late_publisher(
        self, tmp_path: Path
    ) -> None:
        """A stronger claim published DURING the grace is queued behind."""
        weak = make_arbiter(tmp_path, "diet_guard", RANK_DIET_GUARD)
        strong: list[Arbiter] = []
        slept: list[float] = []

        def sleep(seconds: float) -> None:
            slept.append(seconds)
            if not strong:
                strong.append(
                    make_arbiter(tmp_path, "screen_locker", RANK_SCREEN_LOCKER)
                )
            elif len(slept) > 2:
                strong[0].release()

        clock = [0.0]
        base = Timebase(sleep=sleep, now=lambda: clock[0])
        with patch("gatelock._queue.STARTUP_GRACE_SECONDS", 1.5):
            result = wait_for_turn(weak, timebase=base, poll=0.5)
        assert slept[0] == 1.5
        assert result.queued
        assert result.blocked_by == ("screen_locker",)

    def test_zero_grace_does_not_sleep(self, tmp_path: Path) -> None:
        """The fixture's zero skips the sleep entirely."""
        slept: list[float] = []
        base = Timebase(sleep=slept.append, now=lambda: 0.0)
        wait_for_turn(
            make_arbiter(tmp_path, "diet_guard", RANK_DIET_GUARD), timebase=base
        )
        assert slept == []


class TestDropHolder:
    """Dropping the holder lock leaves the claim, and is idempotent."""

    def test_drop_keeps_the_claim_and_frees_the_screen(self, tmp_path: Path) -> None:
        """Another app can take the holder lock; ours is still queued-behind."""
        ours = make_arbiter(tmp_path, "diet_guard", RANK_DIET_GUARD)
        other = make_arbiter(tmp_path, "screen_locker", RANK_SCREEN_LOCKER)
        assert ours.acquire_holder()
        assert not other.acquire_holder()
        ours.drop_holder()
        ours.drop_holder()
        assert not ours.holds_screen
        assert ours.claim.instance_id in {c.instance_id for c in other.live_claims()}
        assert other.acquire_holder()


class TestSetVisible:
    """Hide, and show in creation order."""

    def test_hide_then_show(self, mock_root: MagicMock) -> None:
        """Withdrawn windows come back override-redirect BEFORE they map."""
        _, enumerator, surfaces = build_loop(mock_root, LockConfig(mode="hard"))
        enumerator.scan.return_value = MagicMock(live=(DP0,))
        surfaces.apply(enumerator.scan.return_value)
        window = surfaces._surfaces["DP-0"].window
        window.reset_mock()
        surfaces.set_visible(visible=False)
        window.withdraw.assert_called_once_with()
        window.reset_mock()
        surfaces.set_visible(visible=True)
        names = [c[0] for c in window.method_calls]
        assert names.index("overrideredirect") < names.index("deiconify")
        assert names[-1] == "lift"
        assert call.overrideredirect(boolean=True) in window.method_calls

    def test_soft_mode_is_not_forced_override_redirect(
        self, mock_root: MagicMock
    ) -> None:
        """A managed lock must stay managed."""
        _, enumerator, surfaces = build_loop(mock_root, LockConfig(mode="soft"))
        enumerator.scan.return_value = MagicMock(live=(DP0,))
        surfaces.apply(enumerator.scan.return_value)
        window = surfaces._surfaces["DP-0"].window
        window.reset_mock()
        surfaces.set_visible(visible=True)
        window.overrideredirect.assert_not_called()
