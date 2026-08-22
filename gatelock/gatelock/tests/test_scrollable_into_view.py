"""Tests for scrolling a specific widget into view.

Split from ``test_scrollable.py`` (250-line cap), which keeps the fit states
and the scroll gestures themselves. These cover ``scroll_into_view`` and the
focus-following that calls it.
"""

from __future__ import annotations

import os
import tkinter as tk

import pytest

from gatelock._scrollable import ScrollableSurface
from gatelock._scrollkeys import bind_scroll_keys
from gatelock._userintent import viewport_targets
from gatelock._window import LockConfig

pytestmark = pytest.mark.skipif(
    not os.environ.get("DISPLAY"),
    reason="needs a real X display; run under xvfb-run in a headless checkout",
)

_VIEWPORT_H = 200
_TALL = 60


@pytest.fixture
def surface() -> tk.Misc:
    """A 400x200 viewport holding 20 stacked entries -- deliberately taller."""
    root = tk.Tk()
    # A managed window has its geometry rewritten wholesale by a real window
    # manager (i3 confirmed: a plain geometry() request came back tiled to
    # the pane size instead of 400x200, so nothing ever overflowed and every
    # scroll assertion in this file failed against a real WM session) --
    # exactly the reason production lock windows are overrideredirect too.
    root.overrideredirect(boolean=True)
    root.geometry(f"400x{_VIEWPORT_H}+0+0")
    # No window manager under Xvfb, so the toplevel must claim X input focus
    # before any synthetic key event is delivered anywhere.
    root.focus_force()
    root.update_idletasks()
    made = ScrollableSurface(root, LockConfig())
    made.container.place(relx=0, rely=0, relwidth=1, relheight=1)
    for index in range(_TALL):
        tk.Entry(made.content, name=f"field{index}").pack()
    made.finalize()
    root.update()
    yield made
    root.destroy()


def _offset(made: ScrollableSurface) -> float:
    """The viewport's current scroll fraction."""
    return made.canvas.yview()[0]


def test_scroll_into_view_ignores_an_unmapped_widget(
    surface: ScrollableSurface,
) -> None:
    """A widget Tk has not laid out yet has no position to scroll to."""
    ghost = tk.Entry(surface.content)  # never packed: zero height
    before = _offset(surface)
    surface.scroll_into_view(ghost)
    assert _offset(surface) == before


def test_scroll_into_view_leaves_an_already_visible_widget_alone(
    surface: ScrollableSurface,
) -> None:
    """Nothing moves when the widget is already fully on screen."""
    before = _offset(surface)
    surface.scroll_into_view(surface.content.winfo_children()[0])
    assert _offset(surface) == before


def test_scroll_into_view_reaches_backwards(surface: ScrollableSurface) -> None:
    """Revealing a widget above the viewport scrolls up, not down."""
    surface.canvas.yview_moveto(1.0)
    surface.canvas.update()
    surface.scroll_into_view(surface.content.winfo_children()[0])
    assert _offset(surface) == 0.0


def test_paging_degrades_to_the_canvas_without_a_toplevel(
    surface: ScrollableSurface, caplog: pytest.LogCaptureFixture
) -> None:
    """A widget tree with no real toplevel still scrolls by keyboard.

    Reachable under a mocked Tk root. Binding nothing at all would leave the
    overflow unreachable, so it degrades to canvas-local bindings and says so
    -- a silent degradation here is content the user cannot get to.
    """

    message = "no toplevel"

    def _no_toplevel() -> None:
        raise tk.TclError(message)

    surface.canvas.winfo_toplevel = _no_toplevel
    with caplog.at_level("WARNING"):
        bind_scroll_keys(surface.canvas, surface.content)
        surface._intent.bind(viewport_targets(surface.canvas, surface.content))

    assert "paging keys bound to the canvas only" in caplog.text
    assert "user-input tracking is bound to the viewport only" in caplog.text

    surface.canvas.focus_set()
    surface.canvas.event_generate("<Next>", when="now")
    surface.canvas.update()
    assert _offset(surface) > 0.0


def test_a_second_finalize_does_not_stack_handlers(
    surface: ScrollableSurface,
) -> None:
    """finalize() is documented idempotent, and a repaint calls it again.

    An earlier version re-bound <FocusIn> on every call, so handlers piled up
    one per repaint across the ~19 repaint sites of a single lock session.
    """
    bound_once = set(surface._focus_bound)

    surface.finalize()

    assert set(surface._focus_bound) == bound_once


def test_scroll_into_view_does_nothing_when_everything_fits() -> None:
    """Nothing to reveal on a screen that is fully visible already."""
    root = tk.Tk()
    try:
        root.geometry(f"400x{_VIEWPORT_H}+0+0")
        root.focus_force()
        root.update_idletasks()
        made = ScrollableSurface(root, LockConfig())
        made.container.place(relx=0, rely=0, relwidth=1, relheight=1)
        entry = tk.Entry(made.content)
        entry.pack()
        made.finalize()
        root.update()

        made.scroll_into_view(entry)
        assert made.canvas.yview() == (0.0, 1.0)
    finally:
        root.destroy()


def test_scroll_into_view_holds_still_for_a_widget_in_the_middle(
    surface: ScrollableSurface,
) -> None:
    """A widget already fully on screen is not dragged to an edge.

    The margin logic has three outcomes -- scroll up, scroll down, hold -- and
    "hold" is the one a viewport that jitters would get wrong.
    """
    middle = surface.content.winfo_children()[3]
    before = _offset(surface)

    surface.scroll_into_view(middle)

    assert _offset(surface) == before


def test_the_wheel_scrolls_from_over_the_content(surface: ScrollableSurface) -> None:
    """Wheel-over-text scrolls, which is the only way anyone uses a mouse here.

    Tk dispatches through *bindtags*, not the parent chain: a child's tags are
    ``(itself, its class, the toplevel, "all")``, so a binding on ``content``
    is never consulted for an event over a Label sitting on top of it. Content
    that fills the viewport covers that frame entirely, so binding the wheel
    only on the canvas and the content frame makes wheel scrolling dead
    everywhere the user would actually point.
    """
    child = surface.content.winfo_children()[10]
    before = surface.canvas.yview()[0]

    child.event_generate("<Button-5>")
    surface.canvas.update()

    assert surface.canvas.yview()[0] > before


def test_the_wheel_scrolls_back_up_from_over_the_content(
    surface: ScrollableSurface,
) -> None:
    """The up notch is bound on descendants too, not just the down one."""
    child = surface.content.winfo_children()[10]
    child.event_generate("<Button-5>")
    surface.canvas.update()
    scrolled = surface.canvas.yview()[0]

    child.event_generate("<Button-4>")
    surface.canvas.update()

    assert surface.canvas.yview()[0] < scrolled
