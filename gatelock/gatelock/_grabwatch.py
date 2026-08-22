"""Deciding whether this application still holds the input grab.

Split from :mod:`gatelock._recovery`, which re-asserts the grab when this
says it is gone. The question is subtle enough -- and its history costly
enough -- to be worth reading on its own, and the log-throttling state it
needs is the reason it is a small object rather than a function.
"""

from __future__ import annotations

import logging
import tkinter as tk

_logger = logging.getLogger(__name__)


class GrabWatch:
    """Answers "is the grab still ours?", warning once per distinct cause."""

    def __init__(self, root: tk.Misc) -> None:
        """Watch the grab on `root`'s display.

        Args:
            root: The Tk widget whose display the grab is read from.
        """
        self._root = root
        self._last_warning: str | None = None

    def holds_grab(self) -> bool:
        """Whether the grab is held by a window this application owns.

        Deliberately *not* ``grab_current() is self._root``. Our own transient
        children take the grab for themselves: a posted Tk menu grabs the menu
        window, and the old identity test read that as "the grab was lost" and
        called ``grab_set_global()`` a second later, stealing it back off our
        own widget mid-interaction. That is what made the screen-locker sport
        selector unusable while locked on 2026-07-26. Any window we own still
        means the lock has the pointer and keyboard.

        ``grab_current`` resolves the name Tcl gives it against our own widget
        map, so anything that does not resolve -- a Tcl-created popdown such as
        a ``ttk.Combobox``'s, or a stale name -- raises ``KeyError`` and is NOT
        provably ours. That counts as lost and the grab is re-taken: fail
        closed, because this module exists to keep the lock, and losing a
        popdown beats believing we hold a grab we do not.

        Known limitation: a second ``tk.Tk()`` in the same process reports its
        root as ``"."`` too, which is indistinguishable from ours. The old
        identity test had exactly the same blind spot. ``_heat_skip``'s
        throwaway root is the only other one in screen-locker, and it is
        destroyed before the lock window exists.

        Returns:
            True while a window we own holds the grab.
        """
        try:
            held = self._root.grab_current() is not None
        except KeyError as exc:
            self.warn_once(
                f"the grab is held by {exc.args[0]!r}, not one of our windows"
            )
            return False
        except tk.TclError:
            self.warn_once("could not read the current grab")
            return False
        if held:
            self._last_warning = None
        return held

    def warn_once(self, reason: str) -> None:
        """Warn about a lost grab, but only when the reason changes.

        These states can persist for the whole lock (a dark display, a popdown
        that keeps re-grabbing), and this runs once a second -- warning every
        tick would push a line per second into the journal for as long as it
        lasts. Silence is not the alternative: the first occurrence and every
        change of cause are still logged at WARNING.

        Args:
            reason: Why the grab is not provably ours.
        """
        if reason != self._last_warning:
            _logger.warning("%s; treating it as lost and re-taking it", reason)
            self._last_warning = reason
