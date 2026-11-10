# Copyright (c) 2026 Krzysztof Rudnicki
"""Token-styled Tk labels for the numerals the picker shows (dates, months).

Every colour comes from :mod:`sickdays.gui._tokens`. Buttons, switches and
icons are word-free Canvases in :mod:`sickdays.gui._controls`.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from typing import Final

from sickdays.gui import _tokens as tok

_BOLD_ROLES: Final = frozenset({"title", "subtitle"})


def family(widget: tk.Misc) -> str:
    """The family Tk's default font actually resolves to on this display."""
    return str(tkfont.nametofont("TkDefaultFont", root=widget).actual("family"))


def label(
    parent: tk.Misc,
    text: str,
    role: tok.TypeRole,
    *,
    fg: str = tok.TEXT_ON_DARK,
    name: str = "",
) -> tk.Label:
    """A label on ``parent``'s own background; titles and subtitles are bold."""
    return tk.Label(
        parent,
        name=name,
        text=text,
        fg=fg,
        bg=parent.cget("bg"),
        font=tok.font(family(parent), role, bold=role in _BOLD_ROLES),
        justify="left",
        anchor="w",
    )
