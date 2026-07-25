"""Tests for layered output-change detection."""

from __future__ import annotations

import queue
import tkinter as tk
from unittest.mock import MagicMock, patch

from gatelock._detect import OutputChangeDetector, _RandrEventSource

REAL_START = _RandrEventSource.start


class TestTakePending:
    """Coalescing the push signals."""

    def test_nothing_pending(self, mock_root: MagicMock) -> None:
        """A quiet period reports no change."""
        assert OutputChangeDetector(mock_root).take_pending() is False

    def test_configure_event_sets_the_flag(self, mock_root: MagicMock) -> None:
        """A Tk <Configure> is a change signal."""
        detector = OutputChangeDetector(mock_root)
        detector._on_configure(MagicMock())
        assert detector.take_pending() is True
        assert detector.take_pending() is False

    def test_configure_storm_coalesces(self, mock_root: MagicMock) -> None:
        """Many events drain as one -- no rebuild thrash."""
        detector = OutputChangeDetector(mock_root)
        for _ in range(50):
            detector._on_configure(MagicMock())
        assert detector.take_pending() is True
        assert detector.take_pending() is False

    def test_randr_events_drain(self, mock_root: MagicMock) -> None:
        """Queued RandR notices are consumed."""
        detector = OutputChangeDetector(mock_root)
        detector._queue.put("randr")
        detector._queue.put("randr")
        assert detector.take_pending() is True
        assert detector._queue.empty()


class TestStartStop:
    """Subscription lifecycle."""

    def test_start_binds_configure(self, mock_root: MagicMock) -> None:
        """Starting binds the Tk event."""
        detector = OutputChangeDetector(mock_root)
        detector.start()
        mock_root.bind.assert_called_once()
        assert mock_root.bind.call_args.args[0] == "<Configure>"

    def test_start_without_xlib_still_works(self, mock_root: MagicMock) -> None:
        """The autouse patch makes RandR unavailable; detection still runs."""
        detector = OutputChangeDetector(mock_root)
        detector.start()
        assert detector.randr_active is False

    def test_start_with_randr(self, mock_root: MagicMock) -> None:
        """When RandR subscribes, it is reported active."""
        detector = OutputChangeDetector(mock_root)
        with patch.object(_RandrEventSource, "start", return_value=True):
            detector.start()
        assert detector.randr_active is True

    def test_stop_unbinds(self, mock_root: MagicMock) -> None:
        """Stopping releases the Tk binding."""
        detector = OutputChangeDetector(mock_root)
        mock_root.bind.return_value = "binding-id"
        detector.start()
        detector.stop()
        mock_root.unbind.assert_called_once_with("<Configure>", "binding-id")
        assert detector.randr_active is False

    def test_stop_swallows_tclerror(self, mock_root: MagicMock) -> None:
        """Unbinding a dead widget is not an error."""
        detector = OutputChangeDetector(mock_root)
        mock_root.bind.return_value = "binding-id"
        detector.start()
        mock_root.unbind.side_effect = tk.TclError("gone")
        detector.stop()

    def test_stop_before_start(self, mock_root: MagicMock) -> None:
        """Stopping an unstarted detector is safe."""
        OutputChangeDetector(mock_root).stop()


def _xlib(display: MagicMock) -> dict[str, MagicMock]:
    """A fake python-xlib package exposing ``display``."""
    randr = MagicMock(
        RRScreenChangeNotifyMask=1, RRCrtcChangeNotifyMask=2, RROutputChangeNotifyMask=4
    )
    ext = MagicMock(randr=randr)
    return {
        "Xlib": MagicMock(display=display, ext=ext),
        "Xlib.display": display,
        "Xlib.ext": ext,
        "Xlib.ext.randr": randr,
    }


class TestRandrEventSource:
    """The private-connection watcher."""

    def test_connect_without_xlib(self) -> None:
        """A missing python-xlib degrades to no events."""
        source = _RandrEventSource(queue.Queue())
        with patch.dict("sys.modules", {"Xlib": None}):
            assert source._connect() is False

    def test_connect_subscribes_to_all_three_masks(self) -> None:
        """Screen, CRTC and output changes are all watched."""
        display = MagicMock()
        source = _RandrEventSource(queue.Queue())
        with patch.dict("sys.modules", _xlib(display)):
            assert source._connect() is True
        root = display.Display.return_value.screen.return_value.root
        root.xrandr_select_input.assert_called_once_with(1 | 2 | 4)

    def test_connect_failure_closes_and_reports(self) -> None:
        """A subscription error degrades cleanly."""
        display = MagicMock()
        display.Display.return_value.screen.side_effect = OSError("refused")
        source = _RandrEventSource(queue.Queue())
        with patch.dict("sys.modules", _xlib(display)):
            assert source._connect() is False
        assert source._display is None

    def test_start_returns_false_without_connection(self) -> None:
        """No connection means no thread."""
        source = _RandrEventSource(queue.Queue())
        with patch.object(source, "_connect", return_value=False):
            assert REAL_START(source) is False

    def test_loop_posts_one_notice_per_batch(self) -> None:
        """A burst of X events becomes a single change notice."""
        sink: queue.Queue[str] = queue.Queue()
        source = _RandrEventSource(sink)
        source._display = MagicMock()
        source._display.pending_events.side_effect = [3, 0]
        stop_after = {"n": 0}

        def is_set() -> bool:
            stop_after["n"] += 1
            return stop_after["n"] > 2

        source._stop = MagicMock()
        source._stop.is_set.side_effect = is_set
        with patch(
            "gatelock._detect.select.select", side_effect=[([1], [], []), ([], [], [])]
        ):
            source._loop()
        assert sink.qsize() == 1
        assert source._display.next_event.call_count == 3

    def test_run_closes_on_exit(self) -> None:
        """The thread always drops its connection."""
        source = _RandrEventSource(queue.Queue())
        source._display = MagicMock()
        with patch.object(source, "_loop"):
            source._run()
        assert source._display is None

    def test_stop_joins_thread(self) -> None:
        """Stopping sets the flag and joins."""
        source = _RandrEventSource(queue.Queue())
        thread = MagicMock()
        source._thread = thread
        source.stop()
        thread.join.assert_called_once()
        assert source._thread is None

    def test_close_is_idempotent(self) -> None:
        """Closing twice is safe."""
        source = _RandrEventSource(queue.Queue())
        source._display = MagicMock()
        source._close()
        source._close()

    def test_close_swallows_errors(self) -> None:
        """A failing close does not escape the thread."""
        source = _RandrEventSource(queue.Queue())
        source._display = MagicMock()
        source._display.close.side_effect = OSError("already gone")
        source._close()
        assert source._display is None
