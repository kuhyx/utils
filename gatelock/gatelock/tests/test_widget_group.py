"""A group holds every per-output copy, and survives losing one.

Membership and lifecycle: what a group contains, what ``discard``/``clear``/
``destroy`` each mean, and the guarantee that one destroyed surface cannot
abort a repaint on the others. Focus, reads and bindings live in
``test_widget_group_ops.py``.

Run against real Tk because the central guarantee is about ``TclError`` from
genuinely destroyed widgets. A ``MagicMock`` raises whatever it was told to
raise, so it can only confirm the test author's belief about when Tk fails;
destroying a real widget and then configuring it is the actual condition
these guards exist for.
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


def test_an_empty_group_has_no_first_copy() -> None:
    """Zero outputs is a state the apps reach, not an IndexError."""
    empty: WidgetGroup[tk.Label] = WidgetGroup()

    assert empty.first is None
    assert len(empty) == 0
    assert list(empty) == []
    assert empty.outputs == ()


def test_operations_on_an_empty_group_are_no_ops() -> None:
    """A gate with no connected output must not crash on a repaint."""
    empty: WidgetGroup[tk.Label] = WidgetGroup()

    empty.configure(text="x")
    empty.pack()
    empty.pack_forget()
    empty.focus_set()
    empty.focus_force()
    empty.destroy()

    assert empty.first is None


def test_configure_reaches_every_copy(group: WidgetGroup[tk.Label]) -> None:
    """One logical update lands on all three monitors."""
    group.configure(text="12:30")

    assert [widget.cget("text") for widget in group] == ["12:30"] * 3


def test_config_is_an_alias_for_configure(group: WidgetGroup[tk.Label]) -> None:
    """Tk spells it both ways and the donors were split; both work."""
    group.config(text="aliased")

    assert [widget.cget("text") for widget in group] == ["aliased"] * 3


def test_a_dead_copy_does_not_stop_the_live_ones(
    group: WidgetGroup[tk.Label],
) -> None:
    """The whole point: a destroyed surface must not abort the repaint."""
    doomed = group.first
    assert doomed is not None
    doomed.destroy()

    group.configure(text="after")

    survivors = [widget.cget("text") for widget in group if widget.winfo_exists()]
    assert survivors == ["after", "after"]


def test_discard_drops_only_the_named_output(group: WidgetGroup[tk.Label]) -> None:
    """Tearing down one surface leaves the rest of the group intact."""
    group.discard("HDMI-0")

    assert group.outputs == ("DP-0", "DP-2")
    assert len(group) == 2


def test_discard_does_not_destroy_the_widget(
    root: tk.Tk, group: WidgetGroup[tk.Label]
) -> None:
    """Surface teardown already destroys its tree; twice is a TclError storm."""
    copies = list(group)
    group.discard("HDMI-0")
    root.update_idletasks()

    assert all(widget.winfo_exists() for widget in copies)


def test_discarding_an_unknown_output_is_harmless(
    group: WidgetGroup[tk.Label],
) -> None:
    """An output that was never added can still be torn down."""
    group.discard("VGA-9")

    assert len(group) == 3


def test_clear_empties_without_destroying(
    root: tk.Tk, group: WidgetGroup[tk.Label]
) -> None:
    """Forgetting the copies is distinct from destroying them."""
    copies = list(group)
    group.clear()
    root.update_idletasks()

    assert len(group) == 0
    assert all(widget.winfo_exists() for widget in copies)


def test_destroy_empties_the_group(root: tk.Tk, group: WidgetGroup[tk.Label]) -> None:
    """Destroying really does destroy, and leaves nothing behind."""
    copies = list(group)
    group.destroy()
    root.update_idletasks()

    assert len(group) == 0
    assert not any(widget.winfo_exists() for widget in copies)


def test_iteration_preserves_insertion_order(group: WidgetGroup[tk.Label]) -> None:
    """Order is the order surfaces were built, so reads are deterministic."""
    assert group.outputs == ("DP-0", "HDMI-0", "DP-2")


def test_a_seeded_group_keeps_its_pairs(root: tk.Tk) -> None:
    """Constructing from pairs cannot desynchronise names from widgets.

    The donors kept two parallel lists and one of them could be built with
    widgets but no names, which made its strict zip raise ``ValueError``.
    Pairing makes that unrepresentable.
    """
    label = tk.Label(root)
    seeded = WidgetGroup([("DP-0", label)])

    assert seeded.outputs == ("DP-0",)
    assert seeded.first is label
