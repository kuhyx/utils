# Copyright (c) 2026 Krzysztof Rudnicki
"""Design tokens for the Tk picker, copied from the unified design system.

Source: ``~/src/utils/unified-design-system/DOCS-tokens.md`` -- the same
values as daily-limits' ``_tokens.py`` and gatelock's ``LockPalette``.
gatelock is not imported: its ``__init__`` pulls in the lock machinery, and
this package must stay importable by every headless gate. The hexes are the
frozen shared palette, so a copy cannot drift unnoticed.

A sick day is filled ``cat-2``, as on the phone (``DayMarkColors.sick``):
the categorical ramp leaves the warm wedge, so a sick day can never be read
as the free days' accent or as success/warning/danger.

Font sizes are **pixels**, so :func:`font` returns Tk's negative form (a
positive size means points and renders about a third larger).
"""

from __future__ import annotations

from typing import Final, Literal

# Neutrals (dark theme) + semantic roles.
INK: Final = "#211D1B"
INK_RAISED_1: Final = "#2B2624"
INK_RAISED_2: Final = "#38312E"
LINE_DARK: Final = "#463E3A"
TEXT_ON_DARK: Final = "#ECEAE9"
MUTED_ON_DARK: Final = "#AAA09A"
ACCENT: Final = "#B8862E"
SUCCESS: Final = "#8A9A3C"
DANGER: Final = "#E2585F"
ON_FILL: Final = INK
#: ``cat-2``: a sick day's fill.
SICK: Final = "#398FC0"

#: The phone fades a past day to 38 % opacity; Tk has no alpha, so blend.
PAST_ALPHA: Final = 0.38

# Spacing scale (4px base).
XS: Final = 4
SM: Final = 8
MD: Final = 16
LG: Final = 24

#: Width, in px, that wrapped prose lines break at.
WRAP: Final = 420

TypeRole = Literal["title", "subtitle", "body", "label", "caption"]
_TYPE_PX: Final[dict[TypeRole, int]] = {
    "title": 24,
    "subtitle": 20,
    "body": 16,
    "label": 14,
    "caption": 12,
}


def font(family: str, role: TypeRole, *, bold: bool = False) -> tuple[str, int, str]:
    """A Tk font tuple for ``role`` in ``family``, sized in pixels (negative)."""
    return (family, -_TYPE_PX[role], "bold" if bold else "normal")


def blend(colour: str, onto: str, alpha: float) -> str:
    """``colour`` at ``alpha`` opacity over ``onto``, as an opaque ``#RRGGBB``."""
    top = [int(colour[i : i + 2], 16) for i in (1, 3, 5)]
    under = [int(onto[i : i + 2], 16) for i in (1, 3, 5)]
    mixed = (
        round(t * alpha + u * (1 - alpha)) for t, u in zip(top, under, strict=True)
    )
    return "#" + "".join(f"{channel:02X}" for channel in mixed)
