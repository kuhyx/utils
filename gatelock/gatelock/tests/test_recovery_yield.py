# Copyright (c) 2026 Krzysztof Rudnicki
"""Tests for how a recovery tick treats a blocked grab and a waiting prompt.

The tick must (a) say WHY the re-grab failed, (b) feed the yield policy,
(c) stop lifting the lock over a prompt it is yielding to, and (d) re-raise
the prompt last, so nothing the tick lifted covers it.
"""

from __future__ import annotations

from dataclasses import replace
import logging
import tkinter as tk
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from gatelock._config import LockConfig
from gatelock._prompts import PromptYield
from gatelock.tests.conftest import BOTH, build_loop

if TYPE_CHECKING:
    import pytest

    from gatelock._recovery import RecoveryLoop
    from gatelock._surfaces import SurfaceSet

REASON = "grab failed: another application has grab"


def _with_yield(recovery: RecoveryLoop, policy: MagicMock) -> MagicMock:
    """Swap the loop's prompt policy for a mock."""
    recovery._parts = replace(recovery._parts, prompt_yield=policy)
    return policy


def _policy(*, yielding: bool = False, was_yielding: bool = False) -> MagicMock:
    policy = MagicMock(spec=PromptYield)
    policy.yielding = yielding
    policy.grab_held.return_value = was_yielding
    return policy


def _tick_lifts(surfaces: SurfaceSet) -> int:
    """How many lift() calls the surfaces have seen."""
    return sum(s.window.lift.call_count for s in surfaces._surfaces.values())


class TestBlockedGrab:
    """A failed re-grab is explained and handed to the yield policy."""

    def test_failure_text_is_logged_once(
        self,
        loop: tuple[RecoveryLoop, MagicMock, SurfaceSet],
        mock_root: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Tk's own message names the cause; the same cause is not repeated."""
        recovery, enumerator, _ = loop
        enumerator.scan.return_value = BOTH
        mock_root.grab_current.return_value = None
        mock_root.grab_set_global.side_effect = tk.TclError(REASON)
        with caplog.at_level(logging.WARNING):
            recovery.tick()
            recovery.tick()
        assert caplog.text.count(REASON) == 1

    def test_a_different_cause_is_logged_again(
        self,
        loop: tuple[RecoveryLoop, MagicMock, SurfaceSet],
        mock_root: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """ "Window not viewable" after "another application has grab" is news."""
        recovery, enumerator, _ = loop
        enumerator.scan.return_value = BOTH
        mock_root.grab_current.return_value = None
        with caplog.at_level(logging.WARNING):
            mock_root.grab_set_global.side_effect = tk.TclError(REASON)
            recovery.tick()
            mock_root.grab_set_global.side_effect = tk.TclError("not viewable")
            recovery.tick()
        assert "not viewable" in caplog.text

    def test_failure_feeds_the_policy(
        self, loop: tuple[RecoveryLoop, MagicMock, SurfaceSet], mock_root: MagicMock
    ) -> None:
        """The reason reaches the policy that times the block."""
        recovery, enumerator, _ = loop
        policy = _with_yield(recovery, _policy())
        enumerator.scan.return_value = BOTH
        mock_root.grab_current.return_value = None
        mock_root.grab_set_global.side_effect = tk.TclError(REASON)
        recovery.tick()
        policy.grab_blocked.assert_called_once_with(REASON)


class TestYielding:
    """While a prompt is being yielded to, the lock stops covering it."""

    def test_no_lift_while_yielding(
        self, loop: tuple[RecoveryLoop, MagicMock, SurfaceSet], mock_root: MagicMock
    ) -> None:
        """enforce() still places and maps surfaces, but does not raise them."""
        recovery, enumerator, surfaces = loop
        enumerator.scan.return_value = BOTH
        mock_root.grab_current.return_value = None
        mock_root.grab_set_global.side_effect = tk.TclError(REASON)
        recovery.tick()  # creates the surfaces (a create lifts once)
        _with_yield(recovery, _policy(yielding=True))
        before = _tick_lifts(surfaces)
        recovery.tick()
        assert _tick_lifts(surfaces) == before

    def test_lifts_normally_when_not_yielding(
        self, loop: tuple[RecoveryLoop, MagicMock, SurfaceSet], mock_root: MagicMock
    ) -> None:
        """Anything that is not a known prompt keeps today's behaviour."""
        recovery, enumerator, surfaces = loop
        enumerator.scan.return_value = BOTH
        recovery.tick()
        before = _tick_lifts(surfaces)
        _with_yield(recovery, _policy(yielding=False))
        recovery.tick()
        assert _tick_lifts(surfaces) > before

    def test_settles_last(
        self, loop: tuple[RecoveryLoop, MagicMock, SurfaceSet], mock_root: MagicMock
    ) -> None:
        """The prompt is re-raised after everything else the tick did."""
        recovery, enumerator, _ = loop
        enumerator.scan.return_value = BOTH
        policy = _with_yield(recovery, _policy(yielding=True))
        seen: list[str] = []

        def grab_current() -> MagicMock:
            seen.append("grab")
            return mock_root

        def settle() -> None:
            seen.append("settle")

        policy.settle.side_effect = settle
        mock_root.grab_current.side_effect = grab_current
        recovery.tick()
        assert seen == ["grab", "settle"]

    def test_grab_retaken_lifts_the_lock_again(
        self, loop: tuple[RecoveryLoop, MagicMock, SurfaceSet], mock_root: MagicMock
    ) -> None:
        """The prompt closed, the grab came back: the lock covers everything again."""
        recovery, enumerator, surfaces = loop
        enumerator.scan.return_value = BOTH
        recovery.tick()
        _with_yield(recovery, _policy(yielding=True, was_yielding=True))
        before = _tick_lifts(surfaces)
        mock_root.grab_current.return_value = None  # lost, then re-taken
        recovery.tick()
        assert _tick_lifts(surfaces) > before
        mock_root.lift.assert_called()

    def test_grab_held_is_reported_when_nothing_was_lost(
        self, loop: tuple[RecoveryLoop, MagicMock, SurfaceSet], mock_root: MagicMock
    ) -> None:
        """Holding the grab already (the arming loop took it) also ends the yield."""
        recovery, enumerator, _ = loop
        policy = _with_yield(recovery, _policy())
        enumerator.scan.return_value = BOTH
        mock_root.grab_current.return_value = mock_root
        recovery.tick()
        policy.grab_held.assert_called_once_with()


def test_surface_set_enforce_without_lift(mock_root: MagicMock) -> None:
    """``enforce(lift=False)`` corrects drift but never restacks."""
    recovery, enumerator, surfaces = build_loop(mock_root, LockConfig(mode="hard"))
    enumerator.scan.return_value = BOTH
    recovery.tick()
    window = surfaces._surfaces["DP-0"].window
    window.withdraw()  # unmapped: must be remapped even when not lifting
    window.lift.reset_mock()
    assert surfaces.enforce(lift=False) == ("DP-0",)
    window.deiconify.assert_called()
    window.lift.assert_not_called()


def test_holds_grab_is_the_loops_own_question(
    loop: tuple[RecoveryLoop, MagicMock, SurfaceSet], mock_root: MagicMock
) -> None:
    """The public probe embedders and verification harnesses use."""
    recovery, _, _ = loop
    mock_root.grab_current.return_value = mock_root
    assert recovery.holds_grab() is True
    mock_root.grab_current.return_value = None
    assert recovery.holds_grab() is False


def test_raise_all_leaves_the_root_alone_without_a_backdrop(
    mock_root: MagicMock,
) -> None:
    """A soft, grab-less lock has no backdrop root to lift."""
    config = LockConfig(mode="soft")
    _, _, surfaces = build_loop(mock_root, config)
    surfaces.raise_all()
    mock_root.lift.assert_not_called()
