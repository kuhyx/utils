"""Tests for the keyboard affordances every lock surface depends on.

A lock takes a global grab with no other window on screen: a control that
answers only to the mouse, or a field with no way out, is not an
inconvenience there -- it is a user who cannot satisfy the lock at all.
"""

from __future__ import annotations

import os
import tkinter as tk

import pytest

from gatelock._keyboard import bind_activate, bind_cancel, escape_text_tab_trap

pytestmark = pytest.mark.skipif(
    not os.environ.get("DISPLAY"),
    reason="needs a real X display; run under xvfb-run in a headless checkout",
)


@pytest.fixture
def root() -> tk.Tk:
    """A focused toplevel; synthetic key events go nowhere without focus."""
    made = tk.Tk()
    made.geometry("300x200+0+0")
    made.focus_force()
    made.update()
    yield made
    made.destroy()


def test_enter_and_space_press_a_button(root: tk.Tk) -> None:
    """Tk's X11 class bindings give Button only <space>; Enter does nothing.

    Under a grab with no pointer, "the obvious key does nothing" is the
    difference between satisfying the lock and being stuck at it.
    """
    pressed: list[str] = []
    button = tk.Button(root, text="OK", command=lambda: pressed.append("click"))
    button.pack()
    button.focus_set()
    root.update()

    bind_activate(button)
    button.event_generate("<Return>", when="now")
    root.update()
    assert pressed == ["click"]

    button.event_generate("<KP_Enter>", when="now")
    root.update()
    assert len(pressed) == 2


def test_escape_runs_the_cancel_action(root: tk.Tk) -> None:
    """The declining option needs a key of its own, not just a click target."""
    cancelled: list[str] = []
    bind_cancel(root, lambda: cancelled.append("esc"))

    root.event_generate("<Escape>", when="now")
    root.update()

    assert cancelled == ["esc"]


def test_tab_leaves_a_text_box_instead_of_typing_into_it(root: tk.Tk) -> None:
    """Untreated, Tk makes <Tab> insert a tab and refocus the same widget.

    On a lock surface that is a dead end: the only advertised exits are
    Ctrl+Tab / Ctrl+Shift+Tab, which nothing tells the user about, and the
    submit button sits on the far side of the trap.
    """
    text = tk.Text(root, height=2)
    text.pack()
    after = tk.Entry(root)
    after.pack()
    text.focus_set()
    root.update()

    escape_text_tab_trap(text)
    text.event_generate("<Tab>", when="now")
    root.update()

    assert root.focus_get() is after
    assert text.get("1.0", "end").strip() == ""


def test_shift_tab_goes_back_out_of_a_text_box(root: tk.Tk) -> None:
    """Both directions, including X11's own ISO_Left_Tab keysym."""
    before = tk.Entry(root)
    before.pack()
    text = tk.Text(root, height=2)
    text.pack()
    text.focus_set()
    root.update()

    escape_text_tab_trap(text)
    text.event_generate("<ISO_Left_Tab>", when="now")
    root.update()

    assert root.focus_get() is before
