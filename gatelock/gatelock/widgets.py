"""Composite widgets every gate app was rebuilding from the same tokens.

``LockConfig`` already owns the palette and the type scale, but a palette is
not a component: four apps each turned the same tokens into the same button,
the same section heading and the same body row, and drifted apart doing it.
This module is the shared result, extracted only where two or more repos
already had a structurally similar implementation.

The two traps below are Tk defaults rather than oversights in any one app,
and both copies of the button had to solve them independently:

1. **``<Return>`` does nothing on a ``tk.Button``.** Tk's X11 class bindings
   give the widget ``<space>`` and nothing else, so a focused button is
   Space-only and Enter -- the key a user actually reaches for -- silently
   does nothing. :func:`make_button` binds it.
2. **The default focus ring is 1px black**, which against ``#211D1B`` reads
   as no ring at all, so keyboard users cannot see where focus is. Every
   widget here takes its ring from ``LockConfig.focus_kwargs()``.

See :class:`ButtonStyle` for why emphasis is a ``variant`` and not a colour.
"""

from __future__ import annotations

from dataclasses import dataclass
import tkinter as tk
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Callable

    from gatelock._window import LockConfig, TypeRole

ButtonVariant = Literal["primary", "secondary", "danger"]
"""Emphasis role for :func:`make_button`, not a colour."""


@dataclass(frozen=True, slots=True)
class ButtonStyle:
    """How a button reads: its emphasis role, and whether the label is bold.

    ``variant`` lives here rather than as a loose colour pair because it is
    the whole point of the API: it picks the text colour *from* the fill, so
    a call site structurally cannot pair a foreground with a background it
    does not contrast against.

    Attributes:
        variant: Emphasis role. ``primary`` is the one high-emphasis action
            per screen; ``secondary`` stays low-contrast and ``danger`` reads
            as an alarm.
        bold: Whether the label is bold. Gate buttons are, except for a few
            low-emphasis ones ("Fetch from sync", "Close Demo") that would
            otherwise shout as loudly as the action they sit beside.
    """

    variant: ButtonVariant = "primary"
    bold: bool = True


DEFAULT_WRAP = 880
"""Fallback wrap width for :func:`row`, matching a default window geometry.

Passed in rather than hardcoded because the first version of the status panel
wrapped at a fixed 900px inside a 720px window, so every long explanation ran
off the right edge -- in the one panel whose entire job is explaining things.
"""


@dataclass(frozen=True, slots=True)
class RowStyle:
    """How one :func:`row` reads: its colour, size and wrap width.

    Grouped because they are a single decision made together, and because
    the overwhelmingly common row -- ordinary body text -- passes none of
    them.

    Attributes:
        color: Overrides ``LockConfig.fg``. Status colours are load-bearing
            in a gate: red means the gate is holding you, amber means
            something needs attention, green means clear. Nothing should be
            coloured merely to look lively.
        role: Type-scale role.
        wrap: Wrap width in px, clamped to a usable minimum when applied.
    """

    color: str | None = None
    role: TypeRole = "label"
    wrap: int = DEFAULT_WRAP


# Horizontal padding is 2x vertical (tokens.md "Buttons"; both on the 4px
# spacing scale).
_BUTTON_PADY = 12
_BUTTON_PADX = 24
# Blend fraction toward white for a button's hover/active fill.
_HOVER_LIGHTEN = 0.12
_HEX_CHANNEL_OFFSETS = (1, 3, 5)
_RGB_MAX = 255
# Narrowest wrap worth honouring; below this a "wrapped" line is one word.
_MIN_WRAP = 320


def _lighten(hex_color: str, amount: float = _HOVER_LIGHTEN) -> str:
    """Blend ``hex_color`` toward white by ``amount``, for a hover state."""
    channels = (
        int(hex_color[offset : offset + 2], 16) for offset in _HEX_CHANNEL_OFFSETS
    )
    return "#" + "".join(
        f"{round(channel + (_RGB_MAX - channel) * amount):02x}" for channel in channels
    )


def _button_fills(config: LockConfig) -> dict[ButtonVariant, tuple[str, str]]:
    """Return the fill/text pair for each variant, read from the palette.

    All three pairs use ``on_fill`` (never ``fg``) for text drawn on a filled
    surface, per tokens.md -- which is the whole point of keying off a
    variant instead of letting each call site invent its own hex pair.
    """
    return {
        "primary": (config.accent, config.on_fill),
        "secondary": (config.field_bg, config.fg),
        "danger": (config.danger, config.on_fill),
    }


# The one high-emphasis button per screen reads larger than everything else
# (rule 3: size is another axis of prominence, alongside colour); every other
# variant shares the smaller chrome size.
_BUTTON_ROLES: dict[ButtonVariant, TypeRole] = {
    "primary": "body",
    "secondary": "label",
    "danger": "label",
}


def make_button(
    parent: tk.Misc,
    config: LockConfig,
    text: str,
    command: Callable[[], None],
    style: ButtonStyle | None = None,
) -> tk.Button:
    """Build a button from the shared primary/secondary/danger palette.

    Binds ``<Return>`` and ``<KP_Enter>`` as well as relying on ``command``,
    because Tk gives ``tk.Button`` only ``<space>`` on X11 -- without this
    every button in a gate is Space-only and Enter silently does nothing.

    Args:
        parent: Widget to build into.
        config: Token source for colours, type scale and the focus ring.
        text: The button's label.
        command: Invoked on click, Space, Return and KP_Enter alike.
        style: Emphasis role and label weight. Defaults to a bold primary,
            which is what most gate buttons are.

    Returns:
        The configured button. Not packed -- the caller places it.
    """
    style = style if style is not None else ButtonStyle()
    variant = style.variant
    fill, text_color = _button_fills(config)[variant]
    button = tk.Button(
        parent,
        text=text,
        font=config.font(_BUTTON_ROLES[variant], bold=style.bold),
        bg=fill,
        fg=text_color,
        activebackground=_lighten(fill),
        activeforeground=text_color,
        cursor="hand2",
        padx=_BUTTON_PADX,
        pady=_BUTTON_PADY,
        command=command,
        **config.focus_kwargs(),
    )

    def _activate(_event: tk.Event) -> str:
        button.invoke()
        return "break"

    button.bind("<Return>", _activate, add="+")
    button.bind("<KP_Enter>", _activate, add="+")
    return button


def heading(parent: tk.Misc, config: LockConfig, text: str) -> tk.Label:
    """Build and pack a section title.

    Returns:
        The packed label, so a caller can restyle or destroy it.
    """
    label = tk.Label(
        parent,
        text=text,
        font=config.font("body", bold=True),
        fg=config.accent,
        bg=config.bg,
        anchor="w",
    )
    label.pack(
        fill="x",
        padx=config.space("lg"),
        pady=(config.space("md"), config.space("xs")),
    )
    return label


def row(
    parent: tk.Misc,
    config: LockConfig,
    text: str,
    style: RowStyle | None = None,
) -> tk.Label:
    """Build and pack one line of body text, wrapped to the style's width.

    The three styling options travel together in :class:`RowStyle` rather
    than as loose keywords, because they are one decision ("how does this
    line read?") rather than three, and because a row is written far more
    often than it is restyled -- the common call passes no style at all.

    ``wrap`` lives on the style rather than in module state: the donor kept
    the current width in a module-level dict, which made every row's
    wrapping depend on whichever window rendered most recently.

    Args:
        parent: Widget to build into.
        config: Token source for colours and the type scale.
        text: The line to show.
        style: Colour, type-scale role and wrap width. Defaults to ordinary
            body text at :data:`DEFAULT_WRAP`.

    Returns:
        The packed label.
    """
    style = style if style is not None else RowStyle()
    color, role, wrap = style.color, style.role, style.wrap
    label = tk.Label(
        parent,
        text=text,
        font=config.font(role),
        fg=color if color is not None else config.fg,
        bg=config.bg,
        anchor="w",
        justify="left",
        wraplength=max(_MIN_WRAP, wrap),
    )
    label.pack(fill="x", padx=config.space("xl"), pady=1)
    return label
