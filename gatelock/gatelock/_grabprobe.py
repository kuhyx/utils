# Copyright (c) 2026 Krzysztof Rudnicki
"""Asking X whether the global grab is free, without blocking Tk.

Tk's ``grab -global`` retries internally and blocks the WHOLE event loop for
about 1.0 s on every failed attempt (measured 2026-11-11). The lock retries
every 200 ms and once per recovery tick, so while a foreign client held the
grab (the keyring prompt) the loop was starved: no repaint, no clicks, rows and
buttons without their text.

The probe asks first, on a throwaway python-xlib connection: grab the keyboard
and the pointer on the root with ``GrabModeAsync`` and give them straight
back. ``AlreadyGrabbed`` means somebody else holds one, so the caller skips
Tk's call for this attempt; a failed request costs microseconds instead of a
second. Anything else -- free, or any status or error we do not understand --
means "unknown", and the caller makes today's Tk call: the probe can only ever
*spare* a doomed attempt, never prevent one that might have worked.

Deliberately not part of the ``_recovery_*`` family: it releases the grab it
briefly took, which that family's static invariant forbids by name.
"""

from __future__ import annotations

import contextlib
import logging
import tkinter as tk
from typing import TYPE_CHECKING, Protocol

from gatelock._xlib import load_xlib, xlib_failures

if TYPE_CHECKING:
    from types import ModuleType

    # python-xlib ships no stubs; spell out the surface used (see _randr.py).
    class _XRoot(Protocol):
        def grab_keyboard(self, *args: int | bool) -> int:
            """Mirror ``Window.grab_keyboard()``."""

        def grab_pointer(self, *args: int | bool) -> int:
            """Mirror ``Window.grab_pointer()``."""

    class _XScreen(Protocol):
        root: _XRoot

    class _XDisplay(Protocol):
        def screen(self) -> _XScreen:
            """Mirror ``Display.screen()``."""

        def ungrab_keyboard(self, time: int) -> None:
            """Mirror ``Display.ungrab_keyboard()``."""

        def ungrab_pointer(self, time: int) -> None:
            """Mirror ``Display.ungrab_pointer()``."""

        def sync(self) -> None:
            """Mirror ``Display.sync()``."""


_logger = logging.getLogger(__name__)

_OWNER_EVENTS = True
_NO_EVENTS = 0


class GrabProbe:
    """Answers "is another X client holding the keyboard or pointer?"."""

    def __init__(self) -> None:
        """Start with nothing to repeat."""
        self._last_warning: str | None = None

    def _warn_once(self, message: str) -> None:
        """Warn about a failure, but only when the message changes."""
        if message != self._last_warning:
            _logger.warning("%s", message)
            self._last_warning = message

    def check(self) -> None:
        """Raise ``tk.TclError`` if the grab is known to be held elsewhere.

        Raised as Tk's own exception so the callers keep a single ``except``
        for "could not grab", whoever noticed.
        """
        reason = self.blocked()
        if reason is not None:
            raise tk.TclError(reason)

    def blocked(self) -> str | None:
        """Why the grab cannot be taken right now, or None if unknown or free."""
        modules = load_xlib("Xlib.display", "Xlib.X", "Xlib.error")
        if modules is None:
            self._warn_once("python-xlib is not installed; cannot probe the grab")
            return None
        xdisplay, xconst, xerror = modules
        failures = xlib_failures(xerror)
        try:
            display = xdisplay.Display()
        except failures as exc:
            self._warn_once(f"cannot open an X connection to probe the grab: {exc}")
            return None
        try:
            return _probe(display, xconst)
        except failures as exc:
            self._warn_once(f"probing the grab failed: {exc}")
            return None
        finally:
            with contextlib.suppress(OSError):
                display.close()


def _probe(display: _XDisplay, xconst: ModuleType) -> str | None:
    """Grab keyboard then pointer on the root, release both, report a holder."""
    root = display.screen().root
    modes = (xconst.GrabModeAsync, xconst.GrabModeAsync)
    device = "keyboard"
    status = root.grab_keyboard(_OWNER_EVENTS, *modes, xconst.CurrentTime)
    if status == xconst.GrabSuccess:
        device = "pointer"
        status = root.grab_pointer(
            _OWNER_EVENTS,
            _NO_EVENTS,
            *modes,
            xconst.NONE,
            xconst.NONE,
            xconst.CurrentTime,
        )
    display.ungrab_keyboard(xconst.CurrentTime)
    display.ungrab_pointer(xconst.CurrentTime)
    display.sync()
    if status == xconst.AlreadyGrabbed:
        return f"grab failed: another application has grab ({device}, probed)"
    return None
