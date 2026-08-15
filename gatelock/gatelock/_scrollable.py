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
   :meth:`ScrollableSurface.scroll_into_view` fixes that, but only for focus
   the *user* moved.

Wheel scrolling is bound too, but as an addition -- never as the only path.

**Scrolling is the fallback, not the design.** A lock screen is supposed to
fit its screen; content that overflows is a layout defect, and :meth:`finalize`
logs it at ``warning`` so it gets fixed rather than lived with. While the
content fits -- the normal case -- the scroll region is pinned to the viewport
and the scrollbar is hidden, so the view cannot move at all. When it does
overflow, the view still only moves in response to a keypress, a click or the
wheel: an earlier version followed *programmatic* focus too, and since the apps
re-focus a widget on every repaint, the screen scrolled itself to mid-content
and back while the user was doing nothing (reported 2026-08-03, 1366x768).
"""

from __future__ import annotations

import logging
import time
import tkinter as tk
from typing import TYPE_CHECKING
import weakref

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
# How long a keypress or click keeps ownership of the viewport. Focus that
# arrives within this window is treated as the user's own navigation (Tab,
# clicking a field, a button press that opens the next screen) and may scroll;
# focus set outside it is the app's own doing and must not move anything.
_USER_INPUT_WINDOW_S = 0.25
# Tk reports 1px for a widget it has not laid out yet. Treating that as a real
# viewport height would report every not-yet-mapped surface as overflowing.
_UNMAPPED_VIEWPORT_PX = 1


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
            show_scrollbar: Allow a scrollbar alongside the canvas. It is only
                ever shown while the content actually overflows -- a bar with
                nothing to scroll is chrome that says the screen is bigger than
                it is. Even when False the content stays keyboard-scrollable;
                the bar is a pointer affordance and a visual hint, not the
                mechanism.
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
            # Deliberately not packed here: _apply_fit_state() packs it the
            # moment the content is found to overflow, and nothing else should
            # put a scrollbar on a screen that fits.
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
        # `content` is bound once, here, because it outlives every repaint --
        # binding it in finalize() instead piled up a handler per repaint.
        # Its descendants are bound in finalize(), each exactly once: Tk sends
        # <FocusIn> to the ancestor chain only when the *toplevel* takes X
        # focus, not when focus moves between two fields inside it, so a
        # binding on `content` alone would miss every Tab.
        self.content.bind("<FocusIn>", self._on_descendant_focus, add="+")
        self._focus_bound: weakref.WeakSet[tk.Misc] = weakref.WeakSet()
        self._last_user_input = 0.0
        self._clicked: tk.Misc | None = None
        self._overflowing: bool | None = None
        self._bind_scroll_keys()
        self._bind_user_input()

    def _on_content_resize(self, _event: tk.Event) -> None:
        """Keep the scroll region matched to the content's real size."""
        self._apply_fit_state()

    def _on_canvas_resize(self, event: tk.Event) -> None:
        """Center the content horizontally and match the viewport width.

        Matching the width is what lets ``wraplength`` and ``justify=center``
        behave the same as they did before the viewport was introduced.
        """
        self.canvas.itemconfigure(self._content_id, width=event.width)
        self._apply_fit_state()

    def _apply_fit_state(self) -> None:
        """Switch between "fits" and "overflows" layout.

        Fitting is the normal, intended state: the scroll region is pinned to
        the viewport so *nothing* can scroll, the content is centred, and the
        scrollbar is taken down because there is nothing for it to do.

        Scrolling only exists as the fallback for content that genuinely does
        not fit, and that is a defect worth reporting (see :meth:`finalize`),
        not a layout mode to design for.

        Pinning the region is also what makes centring survive. It used to be
        cancelled: content was centred by moving the canvas *item* down, which
        moved the scroll region's top edge down with it, and the reset in
        :meth:`finalize` then scrolled to that top edge -- putting the content
        back flush against the screen's top edge on every repaint.
        """
        view_h = self.canvas.winfo_height()
        view_w = self.canvas.winfo_width()
        wanted_h = self.content.winfo_reqheight()
        overflowing = wanted_h > view_h
        if overflowing:
            self.canvas.coords(self._content_id, view_w / 2, 0)
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        else:
            top = max(0, (view_h - wanted_h) // 2) if self._center_when_fits else 0
            self.canvas.coords(self._content_id, view_w / 2, top)
            # Region == the *scrollable* area, so yview is exactly (0.0, 1.0)
            # and nothing -- key, wheel or scrollbar -- can move it. The focus
            # ring is drawn outside that area, so it has to come off both
            # dimensions or the region is a hair taller than the viewport and
            # a page-down still nudges the screen.
            inset = 2 * self._border_px()
            self.canvas.configure(
                scrollregion=(0, 0, max(1, view_w - inset), max(1, view_h - inset))
            )
        if overflowing != self._overflowing:
            self._overflowing = overflowing
            self._show_scrollbar(visible=overflowing)

    def _border_px(self) -> int:
        """Width of the canvas's own edge: focus ring plus border."""
        return int(self.canvas.cget("highlightthickness")) + int(
            self.canvas.cget("borderwidth")
        )

    def _show_scrollbar(self, *, visible: bool) -> None:
        """Show the scrollbar only while there is something to scroll."""
        if self._scrollbar is None:
            return
        if visible:
            # Re-packed before the canvas would put it on the wrong side, so
            # the canvas is re-packed after it to keep left/right ordering.
            self._scrollbar.pack(side="right", fill="y")
            self.canvas.pack_forget()
            self.canvas.pack(side="left", fill="both", expand=True)
        else:
            self._scrollbar.pack_forget()

    def _bind_user_input(self) -> None:
        """Record when the user last pressed a key or a mouse button.

        Focus-following scrolling is gated on this: the app focuses widgets
        programmatically on every repaint (and gatelock re-asserts focus from
        its recovery tick), and a viewport that follows *those* moves the
        screen under a user who has touched nothing.
        """
        targets: list[tk.Misc] = [self.canvas, self.content]
        try:
            targets.append(self.canvas.winfo_toplevel())
        except (tk.TclError, KeyError, AttributeError):
            _logger.warning(
                "no toplevel for scroll viewport; user-input tracking is "
                "bound to the viewport only, so focus-following scrolling "
                "stays off unless the viewport itself saw the event"
            )
        for target in targets:
            target.bind("<Key>", self._note_key, add="+")
            target.bind("<Button>", self._note_click, add="+")

    def _note_key(self, _event: tk.Event | None = None) -> None:
        """Timestamp a keypress -- Tab and arrows move focus deliberately."""
        self._last_user_input = time.monotonic()
        self._clicked = None

    def _note_click(self, event: tk.Event | None = None) -> None:
        """Timestamp a click and remember what was clicked."""
        self._last_user_input = time.monotonic()
        self._clicked = getattr(event, "widget", None)

    def _focus_is_user_driven(self, focused: tk.Misc) -> bool:
        """Whether the user, not the app, is responsible for this focus move.

        Time alone is not enough. Clicking "Log Manual Workout" is a user
        event, but the focus that follows belongs to the *next screen*, which
        the app focuses itself while building -- scrolling there is the same
        unasked-for movement as scrolling on a repaint. So a click only counts
        when focus landed on the thing that was clicked; a keypress always
        counts, because Tab and the arrows are how a user moves focus without
        a pointer.
        """
        if time.monotonic() - self._last_user_input > _USER_INPUT_WINDOW_S:
            return False
        if self._clicked is None:
            return True
        return self._clicked is focused

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

    def _track_focus(self, parent: tk.Misc) -> None:
        """Bind <FocusIn> and the wheel on every descendant, each exactly once.

        A repaint destroys and rebuilds the widgets, so this re-runs per
        screen; the WeakSet is what keeps a second :meth:`finalize` on the
        *same* widgets from stacking a second handler on each of them, and
        drops entries as the widgets are destroyed.

        The wheel has to be bound per descendant because Tk dispatches through
        *bindtags*, not the parent chain: a child's tags are ``(itself, its
        class, the toplevel, "all")``, so an event over a Label never reaches
        a binding on ``content``. Content that fills its viewport covers that
        frame completely, which means wheel-over-text -- the only way anyone
        actually scrolls with a mouse -- would do nothing. The donor this
        replaced reached for ``bind_all`` instead, which works but installs
        the handler on *every* widget in the application, including other
        windows' scroll regions.
        """
        for child in parent.winfo_children():
            if child not in self._focus_bound:
                child.bind("<FocusIn>", self._on_descendant_focus, add="+")
                child.bind(_WHEEL_UP, self._line_up, add="+")
                child.bind(_WHEEL_DOWN, self._line_down, add="+")
                self._focus_bound.add(child)
            self._track_focus(child)

    def _on_descendant_focus(self, event: tk.Event) -> None:
        """Reveal a widget the *user* just tabbed or clicked onto.

        Two guards, both of which the earlier version lacked:

        * The move must follow a real keypress or click. Programmatic
          ``focus_set()`` runs on every repaint and from gatelock's recovery
          tick, and following it scrolled the screen under a user who had
          touched nothing -- the reported "scrolls to the bottom and back on
          its own".
        * Only a *leaf* counts. Tk delivers ``<FocusIn>`` to every ancestor of
          the focused widget too, and "scroll this 1643px container into view"
          is not a meaningful request in a 768px viewport -- following those
          is what made one focus change produce three jumps. A widget with
          children is such an ancestor; the focused widget itself is not.
          (Read from the event rather than ``focus_get()``, which reports
          None whenever the toplevel does not currently own X input focus --
          true for every surface behind the one the user is looking at.)
        """
        widget = event.widget
        if widget.winfo_children() or not self._focus_is_user_driven(widget):
            return
        self.scroll_into_view(widget)

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
        """Settle geometry for freshly built content.

        Idempotent -- it re-derives everything from the current content -- so
        it is safe to call again after a repaint.

        The ``yview_moveto(0.0)`` here is offset *initialisation* for new
        content, not a scroll: content that fits cannot be anywhere but 0.0
        (see :meth:`_apply_fit_state`), and content that overflows starts at
        its top. Nothing else in this class moves the viewport unless the user
        asks it to.

        Content that does not fit is reported at ``warning``: the surface is
        supposed to fit its screen, so needing a scrollbar is a layout defect
        to fix, not a mode to live in. ``scripts/verify_screen_fits.py`` in
        each consuming app asserts the same property before it ships.
        """
        self.content.update_idletasks()
        self._track_focus(self.content)
        self._request_content_size()
        self._apply_fit_state()
        self.canvas.yview_moveto(0.0)
        wanted_h = self.content.winfo_reqheight()
        view_h = self.canvas.winfo_height()
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
        """Whether the content currently fits without scrolling.

        Measured the same way :meth:`finalize` and ``gatelock.measure_fit``
        measure it -- the content's *requested* height against the viewport --
        so a caller can never get a different answer than the one the fit
        check gates on. ``bbox("all")`` was the other candidate and disagrees
        while the canvas item is mid-layout.
        """
        self.canvas.update_idletasks()
        return self.content.winfo_reqheight() <= self.canvas.winfo_height()
