# Copyright (c) 2026 Krzysztof Rudnicki
"""Colour derivation for the shared widgets: hover blends and variant fills.

Split from ``widgets.py`` (250-line cap). The seam is deliberate rather than
arbitrary: everything here is pure colour arithmetic over ``LockConfig``, with
no ``tkinter`` import and no widget construction, so it is testable without a
display. ``widgets.py`` keeps the Tk-facing half and re-exports these names,
because :mod:`gatelock.widgets` is the public surface the gate apps import.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from gatelock._window import LockConfig

ButtonVariant = Literal["primary", "secondary", "danger"]
"""Emphasis role for :func:`gatelock.widgets.make_button`, not a colour."""

# Blend fraction toward white for a button's hover/active fill.
_HOVER_LIGHTEN = 0.12
_HEX_CHANNEL_OFFSETS = (1, 3, 5)
_RGB_MAX = 255


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
