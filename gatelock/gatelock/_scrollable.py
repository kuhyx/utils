"""A keyboard-scrollable, focus-following viewport for lock-surface content.

Build it inside a lock surface, pack widgets into :attr:`content`, then call
:meth:`ScrollableSurface.finalize`. Content that fits cannot scroll at all;
content that overflows scrolls by key, click or wheel -- never on its own.

Scrolling is the fallback, not the design: a lock surface is supposed to fit
its screen, and :meth:`ScrollableSurface.finalize` logs an overflow at
``warning`` so it gets fixed. See ``docs/scrollable-viewport.md`` for the
three Tk defaults this exists to prevent and the failures behind each.

Collaborators: :mod:`gatelock._scrollfit` measures and lays out,
:mod:`gatelock._scrollkeys` binds the keys and wheel, and
:mod:`gatelock._userintent` decides whether a focus move was the user's.
"""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING
import weakref

from gatelock._scrollfit import (
    FitTarget,
    apply_fit_state,
    content_span,
    report_overflow,
    request_content_size,
)
from gatelock._scrollkeys import bind_scroll_keys, track_focus
from gatelock._userintent import UserIntentTracker, viewport_targets

if TYPE_CHECKING:
    from gatelock._window import LockConfig

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
        self._intent = UserIntentTracker()
        self._fit = FitTarget(
            canvas=self.canvas,
            content=self.content,
            content_id=self._content_id,
            scrollbar=self._scrollbar,
            center_when_fits=self._center_when_fits,
        )
        bind_scroll_keys(self.canvas, self.content)
        self._intent.bind(viewport_targets(self.canvas, self.content))

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

        Delegates to :func:`gatelock._scrollfit.apply_fit_state`.
        """
        apply_fit_state(self._fit)

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
        if widget.winfo_children() or not self._intent.focus_is_user_driven(widget):
            return
        self.scroll_into_view(widget)

    def scroll_into_view(self, widget: tk.Misc) -> None:
        """Scroll the viewport minimally so ``widget`` is fully visible.

        No-op when the content already fits, or when the widget is not laid
        out yet (a zero height means Tk has not placed it).
        """
        self.canvas.update_idletasks()
        span = content_span(self.canvas)
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
        track_focus(
            self.content, self.canvas, self._on_descendant_focus, self._focus_bound
        )
        request_content_size(self._fit)
        self._apply_fit_state()
        self.canvas.yview_moveto(0.0)
        report_overflow(self._fit)

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
