"""A button the keyboard can actually press, in colours that always contrast.

Run against real Tk: the two defects these widgets exist to prevent are Tk's
own defaults -- ``<Return>`` not being a ``tk.Button`` binding on X11, and a
1px black focus ring that is invisible on the lock palette. A mock reports
whatever it was told, so it cannot fail either check.
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import font as tkfont
from typing import TYPE_CHECKING

import pytest

from gatelock._window import LockConfig
from gatelock.widgets import (
    DEFAULT_WRAP,
    ButtonStyle,
    ButtonVariant,
    RowStyle,
    _lighten,
    heading,
    make_button,
    row,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = pytest.mark.skipif(
    not os.environ.get("DISPLAY"),
    reason="needs a real X display; run under xvfb-run in a headless checkout",
)

_VARIANTS: tuple[ButtonVariant, ...] = ("primary", "secondary", "danger")


def _font_px(widget: tk.Misc) -> int:
    """Return a widget's rendered type size in px.

    ``cget("font")`` gives back Tk's *string* spelling ("Arial -16 bold"),
    not the tuple that was passed in, so the size is read through the font
    object. Tk encodes pixels as a negative size; this returns the magnitude
    so callers can compare sizes the way a reader would.
    """
    return abs(int(tkfont.Font(font=widget.cget("font")).actual("size")))


@pytest.fixture
def root() -> Iterator[tk.Tk]:
    """A focused toplevel; Xvfb has no WM to assign X focus for us."""
    made = tk.Tk()
    made.geometry("600x400+0+0")
    made.focus_force()
    made.update_idletasks()
    yield made
    made.destroy()


@pytest.fixture
def config() -> LockConfig:
    """The default token set."""
    return LockConfig()


def test_return_activates_a_button(root: tk.Tk, config: LockConfig) -> None:
    """Enter invokes the command -- Tk binds only <space> by itself."""
    pressed: list[str] = []
    button = make_button(
        root,
        config,
        "Log",
        lambda: pressed.append("hit"),
    )
    button.pack()
    button.focus_force()
    root.update()

    button.event_generate("<Return>")
    root.update()

    assert pressed == ["hit"]


def test_keypad_enter_activates_a_button(root: tk.Tk, config: LockConfig) -> None:
    """The numeric keypad's Enter is a different keysym, and is bound too."""
    pressed: list[str] = []
    button = make_button(root, config, "Log", lambda: pressed.append("x"))
    button.pack()
    button.focus_force()
    root.update()

    button.event_generate("<KP_Enter>")
    root.update()

    assert pressed == ["x"]


def test_space_still_activates_a_button(root: tk.Tk, config: LockConfig) -> None:
    """Adding <Return> must not displace Tk's own <space> class binding.

    Asserted structurally rather than by ``event_generate``: a synthetic
    ``<space>`` does not drive Tk's *class* bindings under Xvfb -- verified
    against a bare ``tk.Button`` with no gatelock involvement, which ignores
    it too. So a behavioural assertion here would fail for a reason that has
    nothing to do with this widget. ``<Return>`` is bound *instance*-level,
    which is why it can be, and is, exercised for real above.
    """
    button = make_button(root, config, "Log", lambda: None)

    assert "<Key-space>" in button.bind_class("Button")
    assert button.bind_class("Button", "<Key-space>")


@pytest.mark.parametrize("variant", _VARIANTS)
def test_every_variant_draws_text_on_its_own_fill(
    root: tk.Tk, config: LockConfig, variant: ButtonVariant
) -> None:
    """The text colour comes from the fill, so the pair can never mismatch."""
    button = make_button(root, config, "Go", lambda: None, ButtonStyle(variant=variant))

    fill = button.cget("bg")
    text_color = button.cget("fg")
    expected = config.fg if variant == "secondary" else config.on_fill
    assert text_color == expected
    assert fill != text_color


@pytest.mark.parametrize("variant", _VARIANTS)
def test_every_variant_has_a_visible_focus_ring(
    root: tk.Tk, config: LockConfig, variant: ButtonVariant
) -> None:
    """Tk's default ring is 1px black -- invisible on this palette."""
    button = make_button(root, config, "Go", lambda: None, ButtonStyle(variant=variant))

    assert int(button.cget("highlightthickness")) == config.focus_thickness
    assert str(button.cget("highlightcolor")) == config.focus_ring


def test_primary_reads_larger_than_the_other_variants(
    root: tk.Tk, config: LockConfig
) -> None:
    """Size is the second axis of prominence, alongside colour."""
    primary = make_button(root, config, "Go", lambda: None)
    secondary = make_button(
        root, config, "Go", lambda: None, ButtonStyle(variant="secondary")
    )

    # Tk font tuples carry a negative (pixel) size; larger text is more
    # negative, so compare magnitudes.
    assert _font_px(primary) > _font_px(secondary)


def test_bold_is_optional(root: tk.Tk, config: LockConfig) -> None:
    """A caller can opt out of the bold weight."""
    plain = make_button(root, config, "Go", lambda: None, ButtonStyle(bold=False))

    assert "bold" not in str(plain.cget("font"))


def test_the_active_fill_is_lighter_than_the_resting_fill(
    root: tk.Tk, config: LockConfig
) -> None:
    """Hover feedback is a lighter fill, not a glow shadow."""
    button = make_button(root, config, "Go", lambda: None)

    assert button.cget("activebackground") == _lighten(config.accent)
    assert button.cget("activebackground") != button.cget("bg")


def test_lighten_moves_every_channel_toward_white() -> None:
    """Blending is per-channel and clamps at white."""
    assert _lighten("#000000", 0.5) == "#808080"
    assert _lighten("#ffffff", 0.5) == "#ffffff"


def test_heading_uses_the_accent_and_returns_the_label(
    root: tk.Tk, config: LockConfig
) -> None:
    """A section title is accent-coloured and packed."""
    label = heading(root, config, "Right now")

    assert label.cget("text") == "Right now"
    assert str(label.cget("fg")) == config.accent
    assert label.winfo_manager() == "pack"


def test_row_defaults_to_the_body_foreground(root: tk.Tk, config: LockConfig) -> None:
    """An uncoloured row is ordinary text, not a status."""
    label = row(root, config, "Earned all-time: 3")

    assert str(label.cget("fg")) == config.fg
    assert int(label.cget("wraplength")) == DEFAULT_WRAP


def test_row_honours_an_explicit_status_colour(root: tk.Tk, config: LockConfig) -> None:
    """Status colours are load-bearing, so a caller can set one."""
    label = row(root, config, "LOCKED", RowStyle(color=config.danger))

    assert str(label.cget("fg")) == config.danger


def test_row_wraps_at_the_width_it_is_given(root: tk.Tk, config: LockConfig) -> None:
    """Wrap width is a parameter, not module state shared between windows."""
    label = row(root, config, "a long explanation", RowStyle(wrap=500))

    assert int(label.cget("wraplength")) == 500


def test_row_refuses_an_unusably_narrow_wrap(root: tk.Tk, config: LockConfig) -> None:
    """Below the floor a "wrapped" line would be one word per line."""
    label = row(root, config, "text", RowStyle(wrap=10))

    assert int(label.cget("wraplength")) == 320


def test_row_takes_a_type_scale_role(root: tk.Tk, config: LockConfig) -> None:
    """Captions are smaller than the default label role."""
    caption = row(root, config, "note", RowStyle(role="caption"))
    label = row(root, config, "note")

    assert _font_px(caption) < _font_px(label)
