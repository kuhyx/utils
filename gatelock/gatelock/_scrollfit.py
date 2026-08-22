"""Measuring a scroll viewport's content and switching its layout to match.

Split out of :mod:`gatelock._scrollable`, which keeps the widget wiring, focus
tracking and the public surface. Everything here answers one question -- does
the content fit? -- and applies the consequences: pinning or releasing the
scroll region, centring, showing or hiding the scrollbar, and asking for a
canvas big enough to avoid the problem in the first place.

Fitting is the normal, intended state. Scrolling exists only as the fallback
for content that genuinely does not fit, and that is a layout defect worth
reporting, not a mode to design for.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tkinter as tk

_logger = logging.getLogger(__name__)

# Tk reports 1px for a widget it has not laid out yet. Treating that as a real
# viewport height would report every not-yet-mapped surface as overflowing.
_UNMAPPED_VIEWPORT_PX = 1


@dataclass
class FitTarget:
    """The viewport being measured, and the layout knobs that depend on it.

    Attributes:
        canvas: The scroll viewport.
        content: The frame held inside it as a canvas item.
        content_id: The canvas item id of ``content``, whose coords are moved
            to centre the content.
        scrollbar: The scrollbar to show and hide, or None when the surface
            was built without one.
        center_when_fits: Whether content that fits is centred vertically
            rather than pinned to the top.
        overflowing: Last known overflow state, or None before the first
            measurement. Kept so the scrollbar is only re-packed on a genuine
            change rather than on every resize event.
    """

    canvas: tk.Canvas
    content: tk.Frame
    content_id: int
    scrollbar: tk.Scrollbar | None
    center_when_fits: bool
    overflowing: bool | None = field(default=None)


def border_px(canvas: tk.Canvas) -> int:
    """Width of the canvas's own edge: focus ring plus border."""
    return int(canvas.cget("highlightthickness")) + int(canvas.cget("borderwidth"))


def content_span(canvas: tk.Canvas) -> int:
    """Return the scrollable content height in px."""
    box = canvas.bbox("all")
    return (box[3] - box[1]) if box else 0


def show_scrollbar(target: FitTarget, *, visible: bool) -> None:
    """Show the scrollbar only while there is something to scroll.

    Args:
        target: The viewport whose scrollbar is being toggled.
        visible: Whether the scrollbar should be packed.
    """
    if target.scrollbar is None:
        return
    if visible:
        # Re-packed before the canvas would put it on the wrong side, so
        # the canvas is re-packed after it to keep left/right ordering.
        target.scrollbar.pack(side="right", fill="y")
        target.canvas.pack_forget()
        target.canvas.pack(side="left", fill="both", expand=True)
    else:
        target.scrollbar.pack_forget()


def apply_fit_state(target: FitTarget) -> None:
    """Switch between "fits" and "overflows" layout.

    Fitting is the normal, intended state: the scroll region is pinned to
    the viewport so *nothing* can scroll, the content is centred, and the
    scrollbar is taken down because there is nothing for it to do.

    Scrolling only exists as the fallback for content that genuinely does
    not fit, and that is a defect worth reporting (see
    :meth:`gatelock._scrollable.ScrollableSurface.finalize`), not a layout
    mode to design for.

    Pinning the region is also what makes centring survive. It used to be
    cancelled: content was centred by moving the canvas *item* down, which
    moved the scroll region's top edge down with it, and the reset in
    ``finalize`` then scrolled to that top edge -- putting the content
    back flush against the screen's top edge on every repaint.

    Args:
        target: The viewport to measure and re-lay out.
    """
    view_h = target.canvas.winfo_height()
    view_w = target.canvas.winfo_width()
    wanted_h = target.content.winfo_reqheight()
    overflowing = wanted_h > view_h
    if overflowing:
        target.canvas.coords(target.content_id, view_w / 2, 0)
        target.canvas.configure(scrollregion=target.canvas.bbox("all"))
    else:
        top = max(0, (view_h - wanted_h) // 2) if target.center_when_fits else 0
        target.canvas.coords(target.content_id, view_w / 2, top)
        # Region == the *scrollable* area, so yview is exactly (0.0, 1.0)
        # and nothing -- key, wheel or scrollbar -- can move it. The focus
        # ring is drawn outside that area, so it has to come off both
        # dimensions or the region is a hair taller than the viewport and
        # a page-down still nudges the screen.
        inset = 2 * border_px(target.canvas)
        target.canvas.configure(
            scrollregion=(0, 0, max(1, view_w - inset), max(1, view_h - inset))
        )
    if overflowing != target.overflowing:
        target.overflowing = overflowing
        show_scrollbar(target, visible=overflowing)


def request_content_size(target: FitTarget) -> None:
    """Ask for a canvas big enough for the content, clamped to the screen.

    A ``Canvas`` holds its content in a canvas *item*, not as a
    geometry-managed child, so it never propagates the content's requested
    size into its own. A toplevel told to size itself (``geometry("")``)
    therefore has nothing to grow to and stays at its minimum -- which is
    how a 862px-wide button row ended up sheared inside a 700px window even
    after a viewport was added.

    Requesting the content's size fixes that where there is room, and the
    clamp keeps a window from growing off a small display; anything still
    too big scrolls instead of clipping. On a lock surface the container is
    ``place``d at ``relwidth/relheight=1``, which overrides this request --
    correctly, since there the surface size is the screen.

    Args:
        target: The viewport to resize.
    """
    wanted_w = target.content.winfo_reqwidth()
    wanted_h = target.content.winfo_reqheight()
    bar = target.scrollbar.winfo_reqwidth() if target.scrollbar else 0
    target.canvas.configure(
        width=max(1, min(wanted_w, target.canvas.winfo_screenwidth() - bar)),
        height=max(1, min(wanted_h, target.canvas.winfo_screenheight())),
    )


def report_overflow(target: FitTarget) -> None:
    """Log a warning when the content does not fit its viewport.

    The surface is supposed to fit its screen, so needing a scrollbar is a
    layout defect to fix, not a mode to live in.
    ``scripts/verify_screen_fits.py`` in each consuming app asserts the same
    property before it ships.

    Args:
        target: The viewport to measure.
    """
    wanted_h = target.content.winfo_reqheight()
    view_h = target.canvas.winfo_height()
    # A viewport Tk has not laid out yet reports 1px, which is not an
    # overflow -- reporting it would cry wolf on every startup and teach
    # the reader to ignore the one message that matters.
    if view_h > _UNMAPPED_VIEWPORT_PX and wanted_h > view_h:
        _logger.warning(
            "lock content overflows its surface: %dpx of content in a "
            "%dpx viewport (%dpx off-screen); it is reachable only by "
            "scrolling, which no screen should require",
            wanted_h,
            view_h,
            wanted_h - view_h,
        )
