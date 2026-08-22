"""Deciding whether a focus change was driven by the user or by the app.

Split out of :mod:`gatelock._scrollable`, which owns the viewport itself.
Focus-following scrolling has to answer one question -- "did the user just
do something?" -- and getting it wrong is what moves the screen under
someone who has touched nothing.

The tracker owns only the two facts needed to answer it, so the viewport
does not have to carry input bookkeeping alongside its geometry.
"""

from __future__ import annotations

import logging
import time
import tkinter as tk

_logger = logging.getLogger(__name__)

# How long after a keypress or click a focus change still counts as the
# user's doing. Long enough to cover the focus that follows an event,
# short enough not to adopt the next repaint.
_USER_INPUT_WINDOW_S = 0.25


class UserIntentTracker:
    """Records recent user input so focus moves can be attributed to it."""

    def __init__(self) -> None:
        """Start with no recorded input, so nothing counts as user-driven."""
        self._last_user_input = 0.0
        self._clicked: tk.Misc | None = None

    def bind(self, targets: list[tk.Misc]) -> None:
        """Record when the user last pressed a key or a mouse button.

        Focus-following scrolling is gated on this: the app focuses widgets
        programmatically on every repaint (and gatelock re-asserts focus from
        its recovery tick), and a viewport that follows *those* moves the
        screen under a user who has touched nothing.

        Args:
            targets: Widgets to bind on. Bindings are added (``add="+"``) so
                they never displace the app's own handlers.
        """
        for target in targets:
            target.bind("<Key>", self.note_key, add="+")
            target.bind("<Button>", self.note_click, add="+")

    def note_key(self, _event: tk.Event | None = None) -> None:
        """Timestamp a keypress -- Tab and arrows move focus deliberately."""
        self._last_user_input = time.monotonic()
        self._clicked = None

    def note_click(self, event: tk.Event | None = None) -> None:
        """Timestamp a click and remember what was clicked."""
        self._last_user_input = time.monotonic()
        self._clicked = getattr(event, "widget", None)

    def focus_is_user_driven(self, focused: tk.Misc) -> bool:
        """Whether the user, not the app, is responsible for this focus move.

        Time alone is not enough. Clicking "Log Manual Workout" is a user
        event, but the focus that follows belongs to the *next screen*, which
        the app focuses itself while building -- scrolling there is the same
        unasked-for movement as scrolling on a repaint. So a click only counts
        when focus landed on the thing that was clicked; a keypress always
        counts, because Tab and the arrows are how a user moves focus without
        a pointer.

        Args:
            focused: The widget that just took focus.

        Returns:
            True when the focus move should be followed by the viewport.
        """
        if time.monotonic() - self._last_user_input > _USER_INPUT_WINDOW_S:
            return False
        if self._clicked is None:
            return True
        return self._clicked is focused


def viewport_targets(canvas: tk.Misc, content: tk.Misc) -> list[tk.Misc]:
    """The widgets a viewport should watch for user input.

    The toplevel is included when it can be reached, so input anywhere in the
    lock counts; without it, only events on the viewport itself do.

    Args:
        canvas: The scroll viewport.
        content: The frame scrolled inside it.

    Returns:
        The bind targets, most-specific first.
    """
    targets: list[tk.Misc] = [canvas, content]
    try:
        targets.append(canvas.winfo_toplevel())
    except (tk.TclError, KeyError, AttributeError):
        _logger.warning(
            "no toplevel for scroll viewport; user-input tracking is "
            "bound to the viewport only, so focus-following scrolling "
            "stays off unless the viewport itself saw the event"
        )
    return targets
