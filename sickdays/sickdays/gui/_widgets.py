# Copyright (c) 2026 Krzysztof Rudnicki
"""Token-styled Tk building blocks shared by the panel and the window.

Every colour comes from :mod:`sickdays.gui._tokens`, and the text colour of a
filled control is picked from its fill (``on-fill`` on the accent, never the
near-white body text), the bug the design system's README warns about.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from typing import TYPE_CHECKING, Final, Literal

from sickdays.gui import _tokens as tok

if TYPE_CHECKING:
    from collections.abc import Callable

ButtonKind = Literal["primary", "danger", "plain"]
_BOLD_ROLES: Final = frozenset({"title", "subtitle"})

#: (background, foreground) per button kind. Danger is a text button, as on
#: the phone, so its red sits on the dark surface rather than under ink.
_BUTTON_COLOURS: Final[dict[ButtonKind, tuple[str, str]]] = {
    "primary": (tok.ACCENT, tok.ON_FILL),
    "danger": (tok.INK_RAISED_2, tok.DANGER),
    "plain": (tok.INK_RAISED_2, tok.TEXT_ON_DARK),
}


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
    """A label on ``parent``'s own background; prose wraps at :data:`tok.WRAP`.

    Titles and subtitles are bold, everything else regular.
    """
    return tk.Label(
        parent,
        name=name,
        text=text,
        fg=fg,
        bg=parent.cget("bg"),
        font=tok.font(family(parent), role, bold=role in _BOLD_ROLES),
        justify="left",
        anchor="w",
        wraplength=tok.WRAP,
    )


def button(
    parent: tk.Misc,
    text: str,
    command: Callable[[], object],
    *,
    kind: ButtonKind = "plain",
    name: str = "",
) -> tk.Button:
    """A flat button whose text colour follows its fill."""
    bg, fg = _BUTTON_COLOURS[kind]
    return tk.Button(
        parent,
        name=name,
        text=text,
        command=command,
        bg=bg,
        fg=fg,
        activebackground=bg,
        activeforeground=fg,
        font=tok.font(family(parent), "body", bold=kind == "primary"),
        relief="flat",
        borderwidth=0,
        highlightthickness=0,
        padx=tok.MD,
        pady=tok.SM,
        cursor="hand2",
    )


def paint_toggle(switch: tk.Checkbutton, *, on: bool) -> None:
    """Draw ``switch`` as a toggle: accent fill reading "On", or a dark "Off"."""
    bg, fg = (tok.ACCENT, tok.ON_FILL) if on else (tok.INK_RAISED_2, tok.TEXT_ON_DARK)
    switch.configure(
        text="On" if on else "Off",
        bg=bg,
        selectcolor=bg,
        activebackground=bg,
        fg=fg,
        activeforeground=fg,
    )


def toggle(parent: tk.Misc, variable: tk.BooleanVar, *, name: str) -> tk.Checkbutton:
    """A Checkbutton drawn as an On/Off switch, repainted on every change."""
    switch = tk.Checkbutton(
        parent,
        name=name,
        variable=variable,
        onvalue=True,
        offvalue=False,
        indicatoron=False,
        width=4,
        font=tok.font(family(parent), "label", bold=True),
        relief="flat",
        borderwidth=0,
        highlightthickness=0,
        padx=tok.SM,
        pady=tok.XS,
        disabledforeground=tok.MUTED_ON_DARK,
        cursor="hand2",
    )
    switch.configure(command=lambda: paint_toggle(switch, on=variable.get()))
    paint_toggle(switch, on=variable.get())
    return switch
