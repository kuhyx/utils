# Copyright (c) 2026 Krzysztof Rudnicki
"""Design tokens for lock surfaces: palette, type scale and spacing scale.

Split from :mod:`gatelock._config` so that :class:`LockConfig` reads as the
handful of behavioural knobs it is, with the visual vocabulary held by three
records an app overrides as a unit -- a palette is swapped whole, never one
colour at a time.

All defaults come from the ``unified-design-system`` docs
(``~/src/utils/unified-design-system/tokens.md``) -- the same palette used by
every one of kuhy's apps, Flutter and web included.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TypeRole = Literal["display", "title", "subtitle", "body", "label", "caption"]
SpaceStep = Literal["xs", "sm", "md", "lg", "xl", "xxl"]


@dataclass(frozen=True)
class LockPalette:
    """The colours a lock surface is drawn with.

    Attributes:
        bg: Background color for the lock surfaces.
        fg: Primary (near-white) text color.
        muted: Secondary/caption text color.
        field_bg: Background for "raised" surfaces (entry/spinbox fields,
            input wells) -- one step lighter than ``bg``.
        accent: The shared brand accent (buttons, primary actions).
        success: Positive/on-track status color.
        warning: Caution/pending status color.
        danger: Negative/error status color.
        on_fill: Text/icon color for anything drawn on top of a filled
            accent/success/warning/danger surface (e.g. a button's label) --
            NOT ``fg``. All four fills sit in the same mid-light band, so
            near-white text under-contrasts on every one of them; callers
            must pick ``fg`` vs. ``on_fill`` based on the widget's own
            background, never hardcode one for all buttons.
        focus_ring: Color of the *focused* widget's highlight ring. Defaults to
            ``accent``, because Tk's own default is black -- invisible against
            ``bg``. Pass to ``highlightcolor``; note ``highlightbackground`` is
            the *unfocused* ring, so setting that one inverts the affordance.
    """

    bg: str = "#211D1B"
    fg: str = "#ECEAE9"
    muted: str = "#AAA09A"
    field_bg: str = "#2B2624"
    accent: str = "#B8862E"
    success: str = "#8A9A3C"
    warning: str = "#E0A63C"
    danger: str = "#E2585F"
    on_fill: str = "#211D1B"
    focus_ring: str = "#B8862E"


@dataclass(frozen=True)
class LockTypography:
    """The font family and the type scale, in **pixels**.

    Do not pass the sizes to Tk directly -- use :meth:`LockConfig.font`,
    which applies Tk's sign convention (a raw positive value means *points*,
    ~37% bigger).
    """

    font_family: str = "Arial"
    display: int = 32
    title: int = 24
    subtitle: int = 20
    body: int = 16
    label: int = 14
    caption: int = 12


@dataclass(frozen=True)
class LockSpacing:
    """The 4px spacing scale, in pixels, plus the focus-ring width.

    Use the steps for ``padx``/``pady``/``ipadx``. ``focus_thickness`` is the
    ring width in px -- never set it to 0 on a focusable widget.
    """

    xs: int = 4
    sm: int = 8
    md: int = 16
    lg: int = 24
    xl: int = 32
    xxl: int = 48
    focus_thickness: int = 2
