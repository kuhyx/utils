"""The Tkinter credit: an M1 logo button that opens a credit-text panel.

    credit = KuhyCredit(parent)            # a Canvas: pack/grid/place it
    credit.place(relx=1, rely=1, anchor="se")

A click, Enter or Space on the logo opens a small panel (logo + text) placed
in the toplevel next to the logo. A click, Enter or Space on the panel opens
the website through ``opener`` (default: a new browser tab) and closes it.
Escape, a click anywhere else in the window and a second logo click close it.

Tk draws no rounded corners and exposes no accessibility tree, so the radius
token and the accessible name have no Tk form; keyboard focus does.
"""

from __future__ import annotations

import tkinter as tk
import webbrowser
from typing import TYPE_CHECKING

from kuhy_credit._data import (
    DARK,
    FOCUS,
    LIGHT,
    LOGO_FIELD,
    LOGO_SHAPES,
    LOGO_SIZE,
    SPACE_MD,
    SPACE_SM,
    TEXT,
    TEXT_BODY,
    URL,
)

if TYPE_CHECKING:
    from collections.abc import Callable

_THEMES = {"dark": DARK, "light": LIGHT}
_KEYS = ("<Return>", "<space>")


def _draw_logo(canvas: tk.Canvas, size: int) -> None:
    """Draw the field and every logo polygon, scaled to ``size`` px.

    Canvas coordinates start at the outer edge, so the drawing is shifted
    past the focus ring; the field colour is also the canvas background.
    """
    inset = int(canvas.cget("highlightthickness"))
    scale = size / LOGO_SIZE
    canvas.configure(bg=LOGO_FIELD)
    canvas.create_rectangle(inset, inset, inset + size, inset + size, fill=LOGO_FIELD, width=0)
    for fill, points in LOGO_SHAPES:
        coords = [inset + p * scale for p in points]
        canvas.create_polygon(coords, fill=fill, width=0)


def _new_tab(url: str) -> None:
    webbrowser.open(url, new=2)


class KuhyCredit(tk.Canvas):
    """The logo button; owns the panel it opens."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        theme: str = "dark",
        size: int = 48,
        opener: Callable[[str], object] | None = None,
    ) -> None:
        """Build the logo in ``parent`` and the (hidden) panel in its toplevel."""
        if theme not in _THEMES:
            msg = f"theme must be one of {sorted(_THEMES)}, got {theme!r}"
            raise ValueError(msg)
        pal = _THEMES[theme]
        super().__init__(
            parent, width=size, height=size, highlightthickness=2, takefocus=1,
            highlightcolor=FOCUS, highlightbackground=pal["surface"], cursor="hand2",
        )  # fmt: skip
        _draw_logo(self, size)
        self._open_url = opener or _new_tab
        self._top = self.winfo_toplevel()
        self.panel = tk.Frame(
            self._top, bg=pal["surface"], padx=SPACE_MD, pady=SPACE_MD, takefocus=1,
            highlightthickness=1, highlightbackground=pal["border"], highlightcolor=FOCUS,
            cursor="hand2",
        )  # fmt: skip
        self.panel_logo = tk.Canvas(self.panel, width=size, height=size, highlightthickness=0)
        _draw_logo(self.panel_logo, size)
        self.panel_logo.pack(side="left")
        self.label = tk.Label(
            self.panel, text=TEXT, bg=pal["surface"], fg=pal["text"], font=("Arial", -TEXT_BODY)
        )
        self.label.pack(side="left", padx=(SPACE_SM, 0))
        self.is_open = False
        self.bind("<Button-1>", self._toggle)
        for widget in (self.panel, self.panel_logo, self.label):
            widget.bind("<Button-1>", self._activate)
        for key in _KEYS:
            self.bind(key, self._toggle)
            self.panel.bind(key, self._activate)
        self._top.bind("<Escape>", self._escape, add="+")
        self._top.bind("<Button-1>", self._outside, add="+")

    def open(self) -> None:
        """Show the panel beside the logo, on the side with more room."""
        self._top.update_idletasks()
        lx = self.winfo_rootx() - self._top.winfo_rootx()
        ly = self.winfo_rooty() - self._top.winfo_rooty()
        lw, lh = self.winfo_width(), self.winfo_height()
        pw, ph = self.panel.winfo_reqwidth(), self.panel.winfo_reqheight()
        below = ly + lh / 2 < self._top.winfo_height() / 2
        y = ly + lh + SPACE_SM if below else ly - SPACE_SM - ph
        x = lx if lx + lw / 2 < self._top.winfo_width() / 2 else lx + lw - pw
        self.panel.place(x=max(0, x), y=max(0, y))
        self.panel.lift()
        self.panel.focus_set()
        self.is_open = True

    def close(self) -> None:
        """Hide the panel."""
        self.panel.place_forget()
        self.is_open = False

    def _toggle(self, _event: tk.Event | None = None) -> None:
        if self.is_open:
            self.close()
        else:
            self.open()

    def _activate(self, _event: tk.Event | None = None) -> None:
        self.close()
        self._open_url(URL)

    def _escape(self, _event: tk.Event | None = None) -> None:
        if self.is_open:
            self.close()
            self.focus_set()

    def _outside(self, event: tk.Event) -> None:
        if self.is_open and event.widget not in (self, self.panel, self.panel_logo, self.label):
            self.close()
