# Copyright (c) 2026 Krzysztof Rudnicki
"""Word-free controls: an icon button, an on/off switch and an icon slot.

Canvases, because a Tk Button or Checkbutton can only show its state as a
word or a font glyph (see :mod:`sickdays.gui._icons`). Each keeps Tk's own
``state`` option and offers ``invoke()``, so callers and tests drive them
like the widgets they replace. Every state has two channels: shape (icon,
knob position) plus colour.
"""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING, Final, Literal

from sickdays.gui import _tokens as tok
from sickdays.gui._icons import TAG, draw

if TYPE_CHECKING:
    from collections.abc import Callable

ButtonKind = Literal["primary", "danger", "plain"]

#: (fill, icon colour) per button kind; danger keeps its red on a dark fill.
_BUTTON_COLOURS: Final[dict[ButtonKind, tuple[str, str]]] = {
    "primary": (tok.ACCENT, tok.ON_FILL),
    "danger": (tok.INK_RAISED_2, tok.DANGER),
    "plain": (tok.INK_RAISED_2, tok.TEXT_ON_DARK),
}
ICON_PX: Final = 20
_TRACK_W: Final = 44
_TRACK_H: Final = 24


def _enabled(widget: tk.Canvas) -> bool:
    return str(widget.cget("state")) != "disabled"


class IconButton(tk.Canvas):
    """A flat button showing ``icon``; ``invoke()`` runs ``command`` unless disabled."""

    def __init__(
        self,
        parent: tk.Misc,
        icon: str,
        command: Callable[[], object],
        *,
        name: str,
        kind: ButtonKind = "plain",
    ) -> None:
        """Draw the button; a click anywhere on it invokes it."""
        fill, self._colour = _BUTTON_COLOURS[kind]
        super().__init__(
            parent,
            name=name,
            width=ICON_PX + 2 * tok.MD,
            height=ICON_PX + 2 * tok.SM,
            bg=fill,
            highlightthickness=0,
            borderwidth=0,
            cursor="hand2",
        )
        #: Which pictogram this button shows.
        self.icon = icon
        self._command = command
        self.bind("<Button-1>", lambda _event: self.invoke())
        self._paint()

    def set_enabled(self, enabled: bool) -> None:  # noqa: FBT001
        """Grey the icon out and ignore clicks while disabled."""
        self.configure(
            state="normal" if enabled else "disabled",
            cursor="hand2" if enabled else "arrow",
        )
        self._paint()

    def invoke(self) -> None:
        """Run the command, as a click would."""
        if _enabled(self):
            self._command()

    def _paint(self) -> None:
        self.delete(TAG)
        colour = self._colour if _enabled(self) else tok.MUTED_ON_DARK
        draw(self, self.icon, size=ICON_PX, colour=colour, at=(tok.MD, tok.SM))


class Toggle(tk.Canvas):
    """An on/off switch for ``variable``: knob right on accent, left on dark."""

    def __init__(self, parent: tk.Misc, variable: tk.BooleanVar, *, name: str) -> None:
        """Draw the switch in ``variable``'s current state."""
        super().__init__(
            parent,
            name=name,
            width=_TRACK_W,
            height=_TRACK_H,
            bg=parent.cget("bg"),
            highlightthickness=0,
            borderwidth=0,
            cursor="hand2",
        )
        self._variable = variable
        self.bind("<Button-1>", lambda _event: self.invoke())
        self.paint()

    def set_enabled(self, enabled: bool) -> None:  # noqa: FBT001
        """Fade the switch and ignore clicks while disabled."""
        self.configure(
            state="normal" if enabled else "disabled",
            cursor="hand2" if enabled else "arrow",
        )
        self.paint()

    def invoke(self) -> None:
        """Flip the switch, as a click would."""
        if _enabled(self):
            self._variable.set(not self._variable.get())
            self.paint()

    def is_on(self) -> bool:
        """Whether the locker this switch stands for still applies."""
        return bool(self._variable.get())

    def paint(self) -> None:
        """Redraw the track and knob from the variable."""
        self.delete(TAG)
        on = self.is_on()
        track, knob = (
            (tok.ACCENT, tok.ON_FILL) if on else (tok.INK_RAISED_2, tok.MUTED_ON_DARK)
        )
        if not _enabled(self):
            track = tok.blend(track, tok.INK, tok.PAST_ALPHA)
            knob = tok.blend(knob, tok.INK, tok.PAST_ALPHA)
        h, w = _TRACK_H, _TRACK_W
        self.create_oval(0, 0, h, h, fill=track, outline=track, tags=TAG)
        self.create_oval(w - h, 0, w, h, fill=track, outline=track, tags=TAG)
        self.create_rectangle(
            h // 2, 0, w - h // 2, h, fill=track, outline=track, tags=TAG
        )
        left = w - h + 3 if on else 3
        self.create_oval(
            left, 3, left + h - 6, h - 3, fill=knob, outline=knob, tags=TAG
        )


class IconSlot(tk.Canvas):
    """One icon, or nothing: a status mark, a locker's pictogram, a marker."""

    def __init__(self, parent: tk.Misc, *, name: str = "", size: int = ICON_PX) -> None:
        """An empty slot ``size`` px square on ``parent``'s background."""
        super().__init__(
            parent,
            name=name,
            width=size,
            height=size,
            bg=parent.cget("bg"),
            highlightthickness=0,
            borderwidth=0,
        )
        self._size = size
        #: The pictogram shown, or ``None`` when the slot is empty.
        self.icon: str | None = None

    def show(self, icon: str | None, colour: str = tok.TEXT_ON_DARK) -> IconSlot:
        """Show ``icon`` in ``colour`` (``None`` clears the slot)."""
        self.delete(TAG)
        self.icon = icon
        if icon is not None:
            draw(self, icon, size=self._size, colour=colour)
        return self
