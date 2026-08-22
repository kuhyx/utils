"""Tests for focus notification and close on a lock window.

Split from ``test_window_surfaces.py`` to hold the shared 250-line cap.
"""

from __future__ import annotations

import queue
from unittest.mock import MagicMock, patch

from gatelock._arbiter import (
    RANK_DIET_GUARD,
)
from gatelock._detect import _RandrEventSource
from gatelock._outputs import Output, OutputRect
from gatelock._window import LockConfig
from gatelock.tests.conftest import make_window

# Captured before the autouse hermetic fixture replaces it.
REAL_RANDR_START = _RandrEventSource.start

DARK_ONLY = (Output("DP-0", connected=True, rect=None, primary=True),)
TWO_LIVE = (
    Output("DP-0", connected=True, rect=OutputRect(0, 0, 3840, 2160), primary=True),
    Output("HDMI-0", connected=True, rect=OutputRect(3840, 0, 2560, 1440)),
)


class TestFocusNotifiedOnce:
    """Both call sites are load-bearing, so the guard is on the callee."""

    def test_second_notification_is_suppressed(self, mock_root: MagicMock) -> None:
        """The hook fires once even though two timings can reach it."""
        window, hooks = make_window(mock_root, config=LockConfig(mode="hard"))
        window._notify_focus_ready()
        window._notify_focus_ready()
        hooks.on_focus_ready.assert_called_once()


class TestCloseReleasesTheScreen:
    """A clean exit must hand the screen to the next app."""

    def test_arbiter_is_released(self, mock_root: MagicMock) -> None:
        """Without this the alarm -> workout handoff strands the workout lock."""
        arbiter = MagicMock()
        window, _hooks = make_window(mock_root, config=LockConfig(mode="hard"))
        window._arbiter = arbiter
        window.close()
        arbiter.release.assert_called_once_with()

    def test_close_without_arbiter(self, mock_root: MagicMock) -> None:
        """An unarbitrated lock still closes cleanly."""
        window, hooks = make_window(mock_root, config=LockConfig(mode="hard"))
        window.close()
        hooks.on_close.assert_called_once_with()


class TestRemainingBranches:
    """Small paths the other suites do not reach."""

    def test_claim_read_oserror(self, tmp_path: object) -> None:
        """A claim whose contents cannot be read is treated as absent."""
        from gatelock._arbiter import Arbiter

        arbiter = Arbiter("a", RANK_DIET_GUARD, grab="none", disable_vt=False)
        arbiter.publish()
        handle = MagicMock()
        handle.__enter__.return_value = handle
        handle.read.side_effect = OSError("io error")
        with (
            patch("gatelock._arbiter.Path.open", return_value=handle),
            patch("gatelock._claims._try_lock", return_value=False),
        ):
            assert arbiter.live_claims() == ()
        arbiter.release()

    def test_randr_start_spawns_thread(self) -> None:
        """A successful connect starts the watcher thread."""
        source = _RandrEventSource(queue.Queue())
        with (
            patch.object(source, "_connect", return_value=True),
            patch("gatelock._detect.threading.Thread") as thread_cls,
        ):
            assert REAL_RANDR_START(source) is True
        thread_cls.return_value.start.assert_called_once_with()

    def test_randr_loop_ignores_empty_batch(self) -> None:
        """A readable socket with no events posts no notice."""
        sink: queue.Queue[str] = queue.Queue()
        source = _RandrEventSource(sink)
        source._display = MagicMock()
        source._display.pending_events.return_value = 0
        calls = {"n": 0}

        def is_set() -> bool:
            calls["n"] += 1
            return calls["n"] > 1

        source._stop = MagicMock()
        source._stop.is_set.side_effect = is_set
        with patch("gatelock._detect.select.select", return_value=([1], [], [])):
            source._loop()
        assert sink.empty()
