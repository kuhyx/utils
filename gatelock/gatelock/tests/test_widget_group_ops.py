"""Reading a group, focusing it, and binding across it.

Focus is the one operation that deliberately does *not* fan out, and
``first_where`` is how a caller reads back a copy that diverged on purpose.
Membership and lifecycle live in ``test_widget_group.py``.

Run against real Tk: focus delivery and event dispatch are Tk's own
behaviour, which a mock cannot reproduce.
"""

from __future__ import annotations

import os
import tkinter as tk
from typing import TYPE_CHECKING

import pytest

from gatelock.widget_group import WidgetGroup

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = pytest.mark.skipif(
    not os.environ.get("DISPLAY"),
    reason="needs a real X display; run under xvfb-run in a headless checkout",
)


@pytest.fixture
def root() -> Iterator[tk.Tk]:
    """A toplevel to parent the per-output copies."""
    made = tk.Tk()
    made.geometry("400x300+0+0")
    made.focus_force()
    made.update_idletasks()
    yield made
    made.destroy()


@pytest.fixture
def group(root: tk.Tk) -> WidgetGroup[tk.Label]:
    """A label fanned out across three outputs."""
    made: WidgetGroup[tk.Label] = WidgetGroup()
    for name in ("DP-0", "HDMI-0", "DP-2"):
        made.add(name, tk.Label(root, text="start"))
    return made


def test_first_where_finds_the_copy_the_user_typed_on(root: tk.Tk) -> None:
    """Text copies diverge on purpose; this reads back the one in use."""
    entries: WidgetGroup[tk.Entry] = WidgetGroup()
    for name in ("DP-0", "HDMI-0"):
        entries.add(name, tk.Entry(root))
    typed = list(entries)[1]
    typed.insert(0, "chicken")

    found = entries.first_where(lambda widget: bool(widget.get()))

    assert found is typed


def test_first_where_returns_none_when_nothing_matches(root: tk.Tk) -> None:
    """A blank answer everywhere is None, not the first blank copy."""
    entries: WidgetGroup[tk.Entry] = WidgetGroup()
    entries.add("DP-0", tk.Entry(root))

    assert entries.first_where(lambda widget: bool(widget.get())) is None


def test_first_where_skips_a_dead_copy(root: tk.Tk) -> None:
    """A destroyed copy is 'not a match', never an exception."""
    entries: WidgetGroup[tk.Entry] = WidgetGroup()
    for name in ("DP-0", "HDMI-0"):
        entries.add(name, tk.Entry(root))
    live = list(entries)[1]
    live.insert(0, "rice")
    next(iter(entries)).destroy()

    assert entries.first_where(lambda widget: bool(widget.get())) is live


def test_focus_is_singular_not_fanned_out(root: tk.Tk) -> None:
    """X input focus is singular; focusing every copy means the last wins."""
    entries: WidgetGroup[tk.Entry] = WidgetGroup()
    for name in ("DP-0", "HDMI-0", "DP-2"):
        entry = tk.Entry(root)
        entry.pack()
        entries.add(name, entry)
    root.update()

    entries.focus_set()
    root.update()

    assert root.focus_get() is entries.first


def test_focus_skips_a_dead_copy(root: tk.Tk) -> None:
    """Focus lands on the first copy that actually accepts it."""
    entries: WidgetGroup[tk.Entry] = WidgetGroup()
    for name in ("DP-0", "HDMI-0"):
        entry = tk.Entry(root)
        entry.pack()
        entries.add(name, entry)
    root.update()
    survivor = list(entries)[1]
    next(iter(entries)).destroy()

    entries.focus_force()
    root.update()

    assert root.focus_get() is survivor


def test_bind_reaches_every_copy(root: tk.Tk, group: WidgetGroup[tk.Label]) -> None:
    """A binding installed once applies on whichever monitor is clicked."""
    seen: list[str] = []
    group.pack()
    root.update()
    group.bind("<Button-1>", lambda _event: seen.append("hit"))

    for widget in group:
        widget.event_generate("<Button-1>")
    root.update()

    assert seen == ["hit"] * 3


def test_bind_adds_rather_than_replacing(
    root: tk.Tk, group: WidgetGroup[tk.Label]
) -> None:
    """Rebinding on repaint must not silently drop another handler."""
    seen: list[str] = []
    group.pack()
    root.update()
    group.bind("<Button-1>", lambda _event: seen.append("first"))
    group.bind("<Button-1>", lambda _event: seen.append("second"))

    first = group.first
    assert first is not None
    first.event_generate("<Button-1>")
    root.update()

    assert seen == ["first", "second"]


def test_bind_can_replace_when_asked(root: tk.Tk, group: WidgetGroup[tk.Label]) -> None:
    """The additive default is overridable for a caller that means it."""
    seen: list[str] = []
    group.pack()
    root.update()
    group.bind("<Button-1>", lambda _event: seen.append("first"))
    group.bind("<Button-1>", lambda _event: seen.append("only"), add=False)

    first = group.first
    assert first is not None
    first.event_generate("<Button-1>")
    root.update()

    assert seen == ["only"]


def test_pack_and_pack_forget_reach_every_copy(
    root: tk.Tk, group: WidgetGroup[tk.Label]
) -> None:
    """Showing and hiding a logical widget covers every monitor."""
    group.pack()
    root.update_idletasks()
    assert all(widget.winfo_manager() == "pack" for widget in group)

    group.pack_forget()
    root.update_idletasks()
    assert all(widget.winfo_manager() == "" for widget in group)


def test_configure_carries_a_callable(root: tk.Tk) -> None:
    """kwargs is typed `object`, so `command=` survives the fan-out.

    Two donors typed it ``str`` and had to reach past the group to wire a
    button up, which is how a group stops being the single point of update.
    """
    pressed: list[str] = []
    buttons: WidgetGroup[tk.Button] = WidgetGroup()
    for name in ("DP-0", "HDMI-0"):
        buttons.add(name, tk.Button(root, text="go"))

    buttons.configure(command=lambda: pressed.append("hit"))
    for widget in buttons:
        widget.invoke()

    assert pressed == ["hit", "hit"]
