"""The viewport moves for the user, and for nobody else.

These run against real Tk: the behaviour under test is Tk's own focus
delivery and canvas scrolling, which a mock cannot reproduce -- the bug this
file exists to prevent was found precisely because the automatic scrolling
looked correct in every unit test and moved the screen anyway.

On 2026-08-03 the screen locker scrolled itself to mid-content and back with
nobody touching the keyboard: the viewport followed ``<FocusIn>``, the apps
call ``focus_set()`` on every repaint, and Tk delivers ``<FocusIn>`` to every
*ancestor* of the focused widget as well, so one programmatic focus produced
three scrolls aimed at containers taller than the screen.
"""

from __future__ import annotations

import os
import tkinter as tk

import pytest

from gatelock._scrollable import ScrollableSurface
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


def test_the_content_really_overflows(surface: ScrollableSurface) -> None:
    """Guard the fixture: none of the rest means anything if it fits."""
    assert not surface.fits()


def test_programmatic_focus_does_not_scroll(surface: ScrollableSurface) -> None:
    """The regression: the app focusing a widget must not move the view.

    Every repaint focuses something, and gatelock's recovery tick re-asserts
    focus once a second. A viewport that follows those moves the screen under
    a user who has touched nothing.
    """
    target = surface.content.winfo_children()[-1]
    before = _offset(surface)
    target.focus_set()
    surface.canvas.update()
    assert _offset(surface) == before


def test_keyboard_focus_does_scroll(surface: ScrollableSurface) -> None:
    """Tab onto an off-screen field still reveals it.

    The other half of the contract: clipped widgets stay in the tab ring, so
    without this a keyboard user lands on fields they cannot see.
    """
    target = surface.content.winfo_children()[-1]
    before = _offset(surface)
    # Generated on the viewport rather than the field: under Xvfb a synthetic
    # key aimed at an Entry is dropped, and "the user pressed a key" is the
    # whole signal -- which widget received it does not matter.
    surface.canvas.event_generate("<Key-Tab>", when="now")
    target.focus_set()
    surface.canvas.update()
    assert _offset(surface) > before


def test_a_click_elsewhere_does_not_scroll(surface: ScrollableSurface) -> None:
    """A click that opens the next screen is not consent to scroll it.

    Clicking "Log Manual Workout" is a user event, but the focus that follows
    belongs to the screen the app then builds and focuses itself.
    """
    clicked = surface.content.winfo_children()[0]
    target = surface.content.winfo_children()[-1]
    before = _offset(surface)
    clicked.event_generate("<Button-1>", when="now")
    surface.canvas.update()
    target.focus_set()
    surface.canvas.update()
    assert _offset(surface) == before


def test_clicking_a_field_scrolls_to_it(surface: ScrollableSurface) -> None:
    """Clicking a field the user can see is consent to reveal it fully."""
    target = surface.content.winfo_children()[-1]
    before = _offset(surface)
    target.event_generate("<Button-1>", when="now")
    target.focus_set()
    surface.canvas.update()
    assert _offset(surface) > before


def test_keys_and_wheel_scroll(surface: ScrollableSurface) -> None:
    """The user's own scroll gestures work regardless of focus."""
    surface.canvas.focus_set()
    surface.canvas.event_generate("<Next>", when="now")
    surface.canvas.update()
    assert _offset(surface) > 0.0


def test_content_that_fits_cannot_scroll_at_all() -> None:
    """A screen that fits is pinned: no scrollbar, no reachable offset.

    This is the normal case, and it is what makes "no automatic scrolling"
    observable rather than merely intended -- there is nowhere for the view
    to go.
    """
    root = tk.Tk()
    try:
        root.geometry(f"400x{_VIEWPORT_H}+0+0")
        root.focus_force()
        root.update_idletasks()
        made = ScrollableSurface(root, LockConfig())
        made.container.place(relx=0, rely=0, relwidth=1, relheight=1)
        tk.Label(made.content, text="short").pack()
        made.finalize()
        root.update()

        assert made.fits()
        assert made.canvas.yview() == (0.0, 1.0)
        made.canvas.event_generate("<Next>", when="now")
        made.canvas.update()
        assert made.canvas.yview() == (0.0, 1.0)
    finally:
        root.destroy()


def test_every_scroll_gesture_moves_the_view(surface: ScrollableSurface) -> None:
    """PageDown/PageUp, arrows, wheel and End/Home each work on their own.

    Bound across three widgets and two bindtags, so "one of them works" is not
    evidence for the rest -- on a lock with no pointer, a gesture that silently
    does nothing is content the user cannot reach.
    """
    canvas = surface.canvas
    canvas.focus_set()
    surface.canvas.update()

    canvas.event_generate("<Next>", when="now")
    canvas.update()
    paged = _offset(surface)
    assert paged > 0.0

    canvas.event_generate("<Prior>", when="now")
    canvas.update()
    assert _offset(surface) < paged

    canvas.event_generate("<Down>", when="now")
    canvas.update()
    stepped = _offset(surface)
    assert stepped > 0.0

    canvas.event_generate("<Up>", when="now")
    canvas.update()
    assert _offset(surface) < stepped

    canvas.event_generate("<Button-5>", when="now")
    canvas.update()
    wheeled = _offset(surface)
    assert wheeled > 0.0

    canvas.event_generate("<Button-4>", when="now")
    canvas.update()
    assert _offset(surface) < wheeled

    canvas.event_generate("<End>", when="now")
    canvas.update()
    assert _offset(surface) > 0.5

    canvas.event_generate("<Home>", when="now")
    canvas.update()
    assert _offset(surface) == 0.0


def test_a_surface_without_a_scrollbar_still_scrolls() -> None:
    """``show_scrollbar=False`` removes the affordance, not the mechanism."""
    root = tk.Tk()
    try:
        root.geometry(f"400x{_VIEWPORT_H}+0+0")
        root.focus_force()
        root.update_idletasks()
        made = ScrollableSurface(root, LockConfig(), show_scrollbar=False)
        made.container.place(relx=0, rely=0, relwidth=1, relheight=1)
        for index in range(_TALL):
            tk.Entry(made.content, name=f"field{index}").pack()
        made.finalize()
        root.update()

        assert not made.fits()
        made.canvas.focus_set()
        made.canvas.event_generate("<Next>", when="now")
        made.canvas.update()
        assert made.canvas.yview()[0] > 0.0
    finally:
        root.destroy()


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
        surface._bind_scroll_keys()
        surface._bind_user_input()

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
