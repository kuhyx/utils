"""Notice output changes fast, by four means at once.

The lock must react the moment a monitor wakes up, and must not miss a monitor
going dark. No single mechanism covers both cheaply, so all of them run:

1. **RandR events** (``python-xlib``) -- instant and authoritative, catching
   every layout change including ones that leave the screen size unchanged.
2. **Tk ``<Configure>`` on the root** -- zero forks, fires when the X screen's
   bounding box changes. Exactly the signal a monitor coming back produces.
3. **``xrandr --query`` polling** -- the backstop, driven by
   :mod:`gatelock._recovery`, for when ``python-xlib`` is absent.
4. **Tk's own screen dimensions** -- the last-resort floor in
   :mod:`gatelock._outputs`.

Only the first two live here; they are the *push* signals, coalesced into one
"something changed" flag that the recovery loop drains.

**Threading rule, enforced by a test:** Tk is not thread-safe, and a Tk call
from the RandR thread is a hard crash or silent memory corruption. The thread
may only call ``queue.put``. Every Tk touch happens on the drain tick, on the
Tk thread.
"""

from __future__ import annotations

import contextlib
import logging
import queue
import select
import threading
import tkinter as tk
from typing import Any

_logger = logging.getLogger(__name__)

_SELECT_TIMEOUT_S = 0.5
"""How long the RandR thread blocks before re-checking the stop flag."""


class _RandrEventSource:
    """Watches RandR notifications on a private X connection.

    Private on purpose: Xlib connections are not safe to share across threads,
    and :mod:`gatelock._outputs` is using its own on the Tk thread.
    """

    def __init__(self, sink: queue.Queue[str]) -> None:
        """Prepare a source that posts change notices into ``sink``."""
        self._sink = sink
        self._display: Any = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> bool:
        """Begin watching. False if python-xlib is unavailable or refuses."""
        if not self._connect():
            return False
        self._thread = threading.Thread(
            target=self._run, name="gatelock-randr", daemon=True
        )
        self._thread.start()
        return True

    def _connect(self) -> bool:
        """Open the connection and subscribe to layout changes."""
        try:
            from Xlib import display as xdisplay
            from Xlib.ext import randr
        except ImportError:
            _logger.info(
                "python-xlib is not installed; falling back to Tk <Configure> "
                "plus xrandr polling for output-change detection"
            )
            return False
        try:
            self._display = xdisplay.Display()
            root = self._display.screen().root
            root.xrandr_select_input(
                randr.RRScreenChangeNotifyMask
                | randr.RRCrtcChangeNotifyMask
                | randr.RROutputChangeNotifyMask
            )
        except (OSError, ValueError, AttributeError, TypeError) as exc:
            _logger.warning("could not subscribe to RandR events: %s", exc)
            self._close()
            return False
        return True

    def _run(self) -> None:
        """Drain X events until stopped. Touches nothing but the queue."""
        try:
            self._loop()
        except (OSError, ValueError) as exc:  # pragma: no cover - thread teardown
            _logger.debug("RandR watch thread ended: %s", exc)
        finally:
            self._close()

    def _loop(self) -> None:
        """Block on the X socket, posting a notice per batch of events."""
        fileno = self._display.fileno()
        while not self._stop.is_set():
            readable, _, _ = select.select([fileno], [], [], _SELECT_TIMEOUT_S)
            if not readable:
                continue
            pending = self._display.pending_events()
            for _ in range(pending):
                self._display.next_event()
            if pending:
                # One notice per batch: the drain tick re-scans regardless of
                # how many events arrived, so counting them buys nothing.
                self._sink.put("randr")

    def stop(self) -> None:
        """Ask the thread to finish and wait briefly for it."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=_SELECT_TIMEOUT_S * 4)
            self._thread = None

    def _close(self) -> None:
        """Drop the private X connection."""
        if self._display is None:
            return
        with contextlib.suppress(OSError, ValueError, AttributeError):
            self._display.close()
        self._display = None


class OutputChangeDetector:
    """Coalesces every push signal into one drainable "something changed" flag."""

    def __init__(self, root: tk.Misc) -> None:
        """Prepare a detector bound to ``root``; subscribes nothing yet."""
        self._root = root
        self._queue: queue.Queue[str] = queue.Queue()
        self._randr = _RandrEventSource(self._queue)
        self._configure_pending = False
        self._binding: str | None = None
        self._randr_active = False

    @property
    def randr_active(self) -> bool:
        """Whether RandR events are live (so polling can be less eager)."""
        return self._randr_active

    def start(self) -> None:
        """Subscribe to Tk ``<Configure>`` and, if possible, RandR events."""
        self._binding = self._root.bind("<Configure>", self._on_configure, add="+")
        self._randr_active = self._randr.start()
        _logger.info(
            "output-change detection active (randr_events=%s, tk_configure=True)",
            self._randr_active,
        )

    def _on_configure(self, _event: tk.Event[tk.Misc]) -> None:
        """Record that the X screen's geometry changed.

        No debounce needed: this only raises a flag, and the drain tick
        coalesces. A Configure storm sets one boolean many times, and the
        surface diff downstream turns an unchanged layout into a no-op.
        """
        self._configure_pending = True

    def take_pending(self) -> bool:
        """Consume and report whether any change signal has arrived."""
        pending = self._configure_pending
        self._configure_pending = False
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
            pending = True
        return pending

    def stop(self) -> None:
        """Unsubscribe from everything."""
        self._randr.stop()
        self._randr_active = False
        if self._binding is not None:
            with contextlib.suppress(tk.TclError):
                self._root.unbind("<Configure>", self._binding)
            self._binding = None
