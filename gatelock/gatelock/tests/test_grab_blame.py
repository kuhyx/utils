# Copyright (c) 2026 Krzysztof Rudnicki
"""Tests for WHO a blocked grab is blamed on, and the error text that explains it.

Incident 2026-11-11: the lock logged "held by gatelock app 'leetcode_guard'
(pid <its own pid>)" -- it blamed itself, because the holder file it had just
written is the one ``describe_holder`` reads -- while the real holder was the
GNOME Keyring prompt, an ordinary X client. Tk's own error text ("another
application has grab" vs "window not viewable") was swallowed as well.
"""

from __future__ import annotations

from dataclasses import replace
import logging
import os
import tkinter as tk
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from gatelock import _preempt
from gatelock._arbiter import RANK_SCREEN_LOCKER, Arbiter
from gatelock._config import GrabPolicy, LockConfig
from gatelock._prompts import PromptYield
from gatelock.tests.conftest import make_window

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

REASON = "grab failed: another application has grab"


def _own_arbiter(tmp_path: Path) -> Arbiter:
    """A real arbiter that holds the screen, as a running lock does."""
    arbiter = Arbiter(
        "leetcode_guard",
        RANK_SCREEN_LOCKER,
        grab="global",
        disable_vt=True,
        runtime_dir=tmp_path,
    )
    arbiter.publish()
    assert arbiter.acquire_holder()
    return arbiter


class TestNoSelfBlame:
    """When the holder file is our own, the grab holder is somebody else."""

    def test_own_claim_is_not_reported_as_the_holder(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """No "held by gatelock app", no own pid, and a pointer at X clients."""
        arbiter = _own_arbiter(tmp_path)
        config = LockConfig(mode="hard", grab=GrabPolicy(preempt_weaker_holder=True))
        with (
            caplog.at_level(logging.WARNING),
            patch("gatelock._preempt.os.kill") as kill,
        ):
            _preempt.log_grab_blocked(
                25, arbiter=arbiter, config=config, preempted_pids=set()
            )
        arbiter.release()
        assert "held by gatelock app" not in caplog.text
        assert f"pid {os.getpid()}" not in caplog.text
        assert "non-gatelock X client" in caplog.text
        kill.assert_not_called()

    def test_prompt_on_screen_is_named(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A detected credential prompt is named as present, not as a verdict."""
        arbiter = _own_arbiter(tmp_path)
        with caplog.at_level(logging.WARNING):
            _preempt.log_grab_blocked(
                25,
                arbiter=arbiter,
                config=LockConfig(),
                preempted_pids=set(),
                prompt_yield=MagicMock(last_reason="", prompt_names=("gcr-prompter",)),
            )
        arbiter.release()
        assert "gcr-prompter" in caplog.text

    def test_without_arbiter_names_the_prompt_too(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Arbitration disabled: same message, same prompt."""
        with caplog.at_level(logging.WARNING):
            _preempt.log_grab_blocked(
                25,
                arbiter=None,
                config=LockConfig(),
                preempted_pids=set(),
                prompt_yield=MagicMock(last_reason="", prompt_names=("pinentry",)),
            )
        assert "pinentry" in caplog.text
        assert "fullscreen game" in caplog.text

    def test_another_gatelock_app_is_still_named(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Only the self-reference changed: a real foreign holder is still blamed."""
        arbiter = MagicMock()
        arbiter.claim.instance_id = "ours"
        arbiter.describe_holder.return_value = MagicMock(
            app="diet_guard", rank=100, pid=4242, started="t", instance_id="theirs"
        )
        with caplog.at_level(logging.WARNING):
            _preempt.log_grab_blocked(
                25, arbiter=arbiter, config=LockConfig(), preempted_pids=set()
            )
        assert "held by gatelock app 'diet_guard'" in caplog.text


class TestReasonInLogs:
    """Tk's own message rides along on every blocked-grab warning."""

    def test_reason_with_no_gatelock_holder(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The no-holder branch carries it."""
        with caplog.at_level(logging.WARNING):
            _preempt.log_grab_blocked(
                25,
                arbiter=None,
                config=LockConfig(),
                preempted_pids=set(),
                prompt_yield=MagicMock(last_reason=REASON, prompt_names=()),
            )
        assert REASON in caplog.text

    def test_reason_with_a_gatelock_holder(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The holder branch carries it too."""
        arbiter = MagicMock()
        arbiter.claim.instance_id = "ours"
        arbiter.describe_holder.return_value = MagicMock(
            app="diet_guard", rank=100, pid=4242, started="t", instance_id="theirs"
        )
        with caplog.at_level(logging.WARNING):
            _preempt.log_grab_blocked(
                25,
                arbiter=arbiter,
                config=LockConfig(),
                preempted_pids=set(),
                prompt_yield=MagicMock(last_reason=REASON, prompt_names=()),
            )
        assert REASON in caplog.text

    def test_window_passes_the_last_reason_and_prompts(
        self, mock_root: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """``LockWindow`` hands the policy's state to the logger."""
        window, _ = make_window(mock_root, config=LockConfig(mode="hard"))
        stub = MagicMock(last_reason=REASON, prompt_names=("gcr-prompter",))
        window._arming = replace(window._arming, prompt_yield=stub)
        with caplog.at_level(logging.WARNING):
            window._log_grab_blocked(25)
        assert REASON in caplog.text
        assert "gcr-prompter" in caplog.text


class TestArming:
    """The arming retry loop feeds the same policy and surfaces the error."""

    def test_failures_feed_the_policy(self, mock_root: MagicMock) -> None:
        """Each failed attempt records Tk's message."""
        mock_root.grab_set_global.side_effect = tk.TclError(REASON)
        window, _ = make_window(mock_root, config=LockConfig(mode="hard"))
        window._acquire_global_grab(attempt=1)
        assert window._arming.prompt_yield.last_reason == REASON

    def test_local_fallback_warning_has_the_reason(
        self, mock_root: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """``retry_ms=0``: the fallback says why the global grab failed."""
        mock_root.grab_set_global.side_effect = tk.TclError(REASON)
        config = LockConfig(mode="hard", grab=GrabPolicy(retry_ms=0))
        window, _ = make_window(mock_root, config=config)
        with caplog.at_level(logging.WARNING):
            window._acquire_global_grab(attempt=1)
        assert REASON in caplog.text

    def test_success_ends_a_yield_and_relifts_the_lock(
        self, mock_root: MagicMock
    ) -> None:
        """The prompt closed and the retry won: the lock covers the screen again."""
        window, _ = make_window(mock_root, config=LockConfig(mode="hard"))
        policy = MagicMock(spec=PromptYield)
        policy.grab_held.return_value = True
        window._arming = replace(window._arming, prompt_yield=policy)
        window._acquire_global_grab(attempt=3)
        policy.grab_held.assert_called_once_with()
        mock_root.lift.assert_called()

    def test_window_shares_one_policy(self, mock_root: MagicMock) -> None:
        """Arming and recovery must time the same block."""
        window, _ = make_window(mock_root, config=LockConfig(mode="hard"))
        assert window.recovery._parts.prompt_yield is window._arming.prompt_yield
