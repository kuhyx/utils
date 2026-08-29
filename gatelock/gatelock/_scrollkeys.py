"""Keyboard and wheel scrolling for a :class:`~gatelock._scrollable.ScrollableSurface`.

Split out of :mod:`gatelock._scrollable`, which keeps the viewport's geometry
and fit logic. Everything here is about *driving* an existing viewport: the
key and wheel bindings, and the six one-line scroll commands they call.

The commands take the canvas directly rather than the surface, so this module
knows nothing about fit state, focus tracking or scrollbars.
"""

from __future__ import annotations

import logging
import tkinter as tk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, MutableSet

_logger = logging.getLogger(__name__)

# Tk reports wheel notches as Button-4/5 on X11 rather than <MouseWheel>.
_WHEEL_UP = "<Button-4>"
_WHEEL_DOWN = "<Button-5>"

# Lines moved per arrow keypress / wheel notch. Three matches the scroll step
# of a typical toolkit list and keeps a long form from crawling.
_ARROW_UNITS = 3


def page_up(canvas: tk.Canvas) -> None:
    """Scroll up one viewport height."""
    canvas.yview_scroll(-1, "pages")


def page_down(canvas: tk.Canvas) -> None:
    """Scroll down one viewport height."""
    canvas.yview_scroll(1, "pages")


def line_up(canvas: tk.Canvas) -> None:
    """Scroll up one arrow/wheel step."""
    canvas.yview_scroll(-_ARROW_UNITS, "units")


def line_down(canvas: tk.Canvas) -> None:
    """Scroll down one arrow/wheel step."""
    canvas.yview_scroll(_ARROW_UNITS, "units")


def scroll_home(canvas: tk.Canvas) -> None:
    """Jump to the top of the content."""
    canvas.yview_moveto(0.0)


def scroll_end(canvas: tk.Canvas) -> None:
    """Jump to the bottom of the content."""
    canvas.yview_moveto(1.0)


def bind_scroll_keys(canvas: tk.Canvas, content: tk.Misc) -> None:
    """Bind keyboard and wheel scrolling.

    PageUp/PageDown/Home/End go on the *toplevel* where possible: in a
    fullscreen lock those keys have no competing meaning, and binding there
    means they work wherever focus currently sits rather than only when the
    canvas holds it. Arrows bind to the canvas only -- bound globally they
    would fight Listbox, Spinbox and Entry navigation.

    Args:
        canvas: The scroll viewport.
        content: The frame scrolled inside it, bound for the wheel so a notch
            over the content scrolls rather than falling through.
    """

    def on_page_up(_event: tk.Event | None = None) -> None:
        page_up(canvas)

    def on_page_down(_event: tk.Event | None = None) -> None:
        page_down(canvas)

    def on_home(_event: tk.Event | None = None) -> None:
        scroll_home(canvas)

    def on_end(_event: tk.Event | None = None) -> None:
        scroll_end(canvas)

    def on_line_up(_event: tk.Event | None = None) -> None:
        line_up(canvas)

    def on_line_down(_event: tk.Event | None = None) -> None:
        line_down(canvas)

    paging = (
        ("<Prior>", on_page_up),
        ("<Next>", on_page_down),
        ("<Home>", on_home),
        ("<End>", on_end),
    )
    target: tk.Misc = canvas
    try:
        target = canvas.winfo_toplevel()
    except tk.TclError, KeyError, AttributeError:
        # Reachable when the widget tree's root is not a real toplevel --
        # notably under tests that mock the Tk root. Degrade to binding on
        # the canvas rather than failing to build the viewport at all:
        # paging then works while the viewport has focus, which is strictly
        # better than no keyboard scrolling. Logged rather than swallowed
        # so a production occurrence is visible.
        _logger.warning(
            "no toplevel for scroll viewport; paging keys bound to the "
            "canvas only, so they work only while it holds focus"
        )
    for seq, handler in paging:
        target.bind(seq, handler, add="+")

    canvas.bind("<Up>", on_line_up, add="+")
    canvas.bind("<Down>", on_line_down, add="+")
    for seq, handler in ((_WHEEL_UP, on_line_up), (_WHEEL_DOWN, on_line_down)):
        canvas.bind(seq, handler, add="+")
        content.bind(seq, handler, add="+")


def bind_wheel(widget: tk.Misc, canvas: tk.Canvas) -> None:
    """Bind wheel scrolling on one descendant of a viewport.

    A widget that handles its own events (a Listbox, an Entry) otherwise
    swallows the notch, so the wheel appears dead over exactly the parts of a
    form the user is most likely to be pointing at.

    Args:
        widget: The descendant to bind on.
        canvas: The viewport the notch should scroll.
    """

    def on_line_up(_event: tk.Event | None = None) -> None:
        line_up(canvas)

    def on_line_down(_event: tk.Event | None = None) -> None:
        line_down(canvas)

    widget.bind(_WHEEL_UP, on_line_up, add="+")
    widget.bind(_WHEEL_DOWN, on_line_down, add="+")


def track_focus(
    parent: tk.Misc,
    canvas: tk.Canvas,
    on_focus: Callable[[tk.Event], None],
    bound: MutableSet[tk.Misc],
) -> None:
    """Bind <FocusIn> and the wheel on every descendant, each exactly once.

    A repaint destroys and rebuilds the widgets, so this re-runs per screen;
    ``bound`` is what keeps a second ``finalize`` on the *same* widgets from
    stacking a second handler on each of them.

    The wheel has to be bound per descendant because Tk dispatches through
    *bindtags*, not the parent chain: a child's tags are ``(itself, its
    class, the toplevel, "all")``, so an event over a Label never reaches
    a binding on ``content``. Content that fills its viewport covers that
    frame completely, which means wheel-over-text -- the only way anyone
    actually scrolls with a mouse -- would do nothing. The donor this
    replaced reached for ``bind_all`` instead, which works but installs
    the handler on *every* widget in the application, including other
    windows' scroll regions.

    Args:
        parent: Widget whose descendants are bound, recursively.
        canvas: The viewport the wheel should scroll.
        on_focus: Handler bound to each descendant's ``<FocusIn>``.
        bound: Widgets already bound; a WeakSet, so entries drop as widgets
            are destroyed. Mutated in place.
    """
    for child in parent.winfo_children():
        if child not in bound:
            child.bind("<FocusIn>", on_focus, add="+")
            bind_wheel(child, canvas)
            bound.add(child)
        track_focus(child, canvas, on_focus, bound)
