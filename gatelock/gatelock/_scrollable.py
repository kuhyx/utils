"""A keyboard-scrollable, focus-following viewport for lock-surface content.

Lock surfaces cannot solve "content taller than the screen" the obvious way.
A scrollable dialog would be a second ``Toplevel``, and on an
override-redirect lock surface a second toplevel steals the Tk grab, which the
recovery tick then kills a second later -- the 2026-07-26 failure where a
frozen sport selector logged a walk as table tennis. So the viewport has to
live inside the surface's own widget tree, which is what this provides.

Three defects this exists to prevent, all of them Tk defaults rather than
oversights in any one app:

1. **Centered content clips symmetrically.** A ``place``-centered frame takes
   its *requested* size, so when it is too tall the parent shears equal
   amounts off the top *and* the bottom -- losing the header and the submit
   button together, with no scrollbar and no hint anything is missing. This
   top-anchors content inside a scroll region instead.
2. **A Canvas viewport is not keyboard-scrollable.** ``tk.Canvas`` has no
   class-level key bindings at all, so ``::tk::FocusOK`` rejects it as a focus
   stop and the only way to move the view is dragging the scrollbar thumb with
   a pointer. This makes the canvas focusable and binds PageUp/PageDown,
   Home/End and arrows.
3. **Focus walks into invisible widgets.** Canvas clipping does not *unmap* a
   child, so every scrolled-out-of-view field stays ``winfo viewable`` and
   stays in the tab chain, while Tk never scrolls to follow focus. Tabbing
   therefore lands on fields the user cannot see and cannot bring into view.
   :meth:`ScrollableSurface.track_focus` fixes that by scrolling the focused
   widget into view.

Wheel scrolling is bound too, but as an addition -- never as the only path.
"""

from __future__ import annotations

import logging
import tkinter as tk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gatelock._window import LockConfig

_logger = logging.getLogger(__name__)

# Tk reports wheel notches as Button-4/5 on X11 rather than <MouseWheel>.
_WHEEL_UP = "<Button-4>"
_WHEEL_DOWN = "<Button-5>"
# Scroll step in "units" for arrow keys; pages use the viewport height.
_ARROW_UNITS = 3
# Extra px kept visible around a widget scrolled into view, so a focused
# field never sits flush against the viewport edge.
_FOCUS_MARGIN_PX = 12


class ScrollableSurface:
    """A scroll viewport whose content is reachable by keyboard alone.

    Build it inside a lock surface, pack widgets into :attr:`content`, then
    call :meth:`finalize` once the content exists.

    Attributes:
        container: The frame to place/pack into the parent surface.
        canvas: The clipping viewport. Focusable, unlike a bare Canvas.
        content: The frame to build UI into.
    """

    def __init__(
        self,
        parent: tk.Misc,
        config: LockConfig,
        *,
        show_scrollbar: bool = True,
        center_when_fits: bool = False,
    ) -> None:
        """Create the viewport.

        Args:
            parent: The surface (or notebook tab) to build inside.
            config: Token source for colors and the focus ring.
            show_scrollbar: Draw a scrollbar alongside the canvas. Even when
                False the content stays keyboard-scrollable; the bar is a
                pointer affordance and a visual hint, not the mechanism.
            center_when_fits: Vertically centre the content while it fits, and
                fall back to top-anchored scrolling once it does not. This lets
                a viewport replace a ``place``-centred frame without changing
                how short screens look, while removing the failure mode that
                made centring dangerous -- a centred frame that overflows is
                clipped at *both* edges at once, losing the heading and the
                submit button together with no scrollbar to recover either.
        """
        self._config = config
        self._center_when_fits = center_when_fits
        self.container = tk.Frame(parent, bg=config.bg)
        self.canvas = tk.Canvas(
            self.container,
            bg=config.bg,
            highlightthickness=config.focus_thickness,
            highlightcolor=config.focus_ring,
            highlightbackground=config.bg,
            borderwidth=0,
            # Tk gives Canvas no key bindings, so it is not a focus stop by
            # default and the viewport becomes pointer-only. Opt in.
            takefocus=True,
        )
        self._scrollbar: tk.Scrollbar | None = None
        if show_scrollbar:
            self._scrollbar = tk.Scrollbar(
                self.container,
                orient="vertical",
                command=self.canvas.yview,
                # A Scrollbar has key bindings, so it lands in the tab ring --
                # and would otherwise keep Tk's black default ring, invisible
                # against bg. It stays focusable rather than being opted out:
                # its own Prior/Next/arrow class bindings are a legitimate
                # second way to scroll.
                **config.focus_kwargs(),
            )
            self._scrollbar.pack(side="right", fill="y")
            self.canvas.configure(yscrollcommand=self._scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)

        self.content = tk.Frame(self.canvas, bg=config.bg)
        # anchor="n": top-anchored, so overflow scrolls instead of shearing
        # the header and the submit button off opposite edges.
        self._content_id = self.canvas.create_window(
            (0, 0), window=self.content, anchor="n"
        )
        self.content.bind("<Configure>", self._on_content_resize, add="+")
        self.canvas.bind("<Configure>", self._on_canvas_resize, add="+")
        self._bind_scroll_keys()

    def _on_content_resize(self, _event: tk.Event) -> None:
        """Keep the scroll region matched to the content's real size."""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._reposition()

    def _on_canvas_resize(self, event: tk.Event) -> None:
        """Center the content horizontally and match the viewport width.

        Matching the width is what lets ``wraplength`` and ``justify=center``
        behave the same as they did before the viewport was introduced.
        """
        self.canvas.itemconfigure(self._content_id, width=event.width)
        self._reposition()

    def _reposition(self) -> None:
        """Place the content window, centring vertically only while it fits."""
        width = self.canvas.winfo_width()
        top = 0
        if self._center_when_fits:
            spare = self.canvas.winfo_height() - self.content.winfo_reqheight()
            top = max(0, spare // 2)
        self.canvas.coords(self._content_id, width / 2, top)

    def _bind_scroll_keys(self) -> None:
        """Bind keyboard and wheel scrolling.

        PageUp/PageDown/Home/End go on the *toplevel* where possible: in a
        fullscreen lock those keys have no competing meaning, and binding there
        means they work wherever focus currently sits rather than only when the
        canvas holds it. Arrows bind to the canvas only -- bound globally they
        would fight Listbox, Spinbox and Entry navigation.
        """
        paging = (
            ("<Prior>", self._page_up),
            ("<Next>", self._page_down),
            ("<Home>", self._scroll_home),
            ("<End>", self._scroll_end),
        )
        target: tk.Misc = self.canvas
        try:
            target = self.canvas.winfo_toplevel()
        except (tk.TclError, KeyError, AttributeError):
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
        self.canvas.bind("<Up>", self._line_up, add="+")
        self.canvas.bind("<Down>", self._line_down, add="+")
        for seq, handler in (
            (_WHEEL_UP, self._line_up),
            (_WHEEL_DOWN, self._line_down),
        ):
            self.canvas.bind(seq, handler, add="+")
            self.content.bind(seq, handler, add="+")

    def _page_up(self, _event: tk.Event | None = None) -> None:
        self.canvas.yview_scroll(-1, "pages")

    def _page_down(self, _event: tk.Event | None = None) -> None:
        self.canvas.yview_scroll(1, "pages")

    def _line_up(self, _event: tk.Event | None = None) -> None:
        self.canvas.yview_scroll(-_ARROW_UNITS, "units")

    def _line_down(self, _event: tk.Event | None = None) -> None:
        self.canvas.yview_scroll(_ARROW_UNITS, "units")

    def _scroll_home(self, _event: tk.Event | None = None) -> None:
        self.canvas.yview_moveto(0.0)

    def _scroll_end(self, _event: tk.Event | None = None) -> None:
        self.canvas.yview_moveto(1.0)

    def track_focus(self, widget: tk.Misc | None = None) -> None:
        """Scroll the focused descendant into view, recursively binding.

        Call after the content is built. Every descendant gets a ``<FocusIn>``
        handler, because a clipped widget stays in the tab chain: without this,
        Tab walks the user onto fields that are scrolled out of sight with no
        keyboard way to reveal them.

        Args:
            widget: Subtree root to bind. Defaults to :attr:`content`.
        """
        target = self.content if widget is None else widget
        target.bind("<FocusIn>", self._on_descendant_focus, add="+")
        for child in target.winfo_children():
            self.track_focus(child)

    def _on_descendant_focus(self, event: tk.Event) -> None:
        """Scroll so the newly focused widget is fully visible."""
        self.scroll_into_view(event.widget)

    def scroll_into_view(self, widget: tk.Misc) -> None:
        """Scroll the viewport minimally so ``widget`` is fully visible.

        No-op when the content already fits, or when the widget is not laid
        out yet (a zero height means Tk has not placed it).
        """
        self.canvas.update_idletasks()
        span = self._content_span()
        view_h = self.canvas.winfo_height()
        if span <= view_h or widget.winfo_height() <= 0:
            return
        top = widget.winfo_rooty() - self.content.winfo_rooty()
        bottom = top + widget.winfo_height()
        offset = self.canvas.canvasy(0)
        margin = _FOCUS_MARGIN_PX
        if top - margin < offset:
            target = max(0, top - margin)
        elif bottom + margin > offset + view_h:
            target = min(span - view_h, bottom + margin - view_h)
        else:
            return
        self.canvas.yview_moveto(target / span)

    def _content_span(self) -> int:
        """Return the scrollable content height in px."""
        box = self.canvas.bbox("all")
        return (box[3] - box[1]) if box else 0

    def finalize(self) -> None:
        """Settle geometry, wire focus-following, and reset to the top.

        Idempotent, so it is safe to call again after the content changes.
        """
        self.content.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._request_content_size()
        self.track_focus()
        self.canvas.yview_moveto(0.0)
        self._reposition()

    def _request_content_size(self) -> None:
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
        """
        wanted_w = self.content.winfo_reqwidth()
        wanted_h = self.content.winfo_reqheight()
        bar = self._scrollbar.winfo_reqwidth() if self._scrollbar else 0
        self.canvas.configure(
            width=max(1, min(wanted_w, self.canvas.winfo_screenwidth() - bar)),
            height=max(1, min(wanted_h, self.canvas.winfo_screenheight())),
        )

    def fits(self) -> bool:
        """Whether the content currently fits without scrolling."""
        self.canvas.update_idletasks()
        return self._content_span() <= self.canvas.winfo_height()
