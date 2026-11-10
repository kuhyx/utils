# Copyright (c) 2026 Krzysztof Rudnicki
"""Pictograms drawn as Canvas geometry, so the picker needs no words.

Drawn rather than typed: the venv's Tk falls back to core X fonts, where
every non-ASCII glyph (angle quotes, check marks) renders as nothing; the
old month arrows were blank buttons. Each icon is plotted on a unit square,
scaled to ``size`` pixels, and tagged ``icon`` so a repaint can drop it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from sickdays._constants import (
    LOCKER_ALARM,
    LOCKER_BOOK,
    LOCKER_DIET,
    LOCKER_FOCUS,
    LOCKER_LEETCODE,
    LOCKER_WORKOUT,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    import tkinter as tk

TAG: Final = "icon"


class Pen:
    """Draws unit-square coordinates onto ``canvas`` at ``(x, y)``, ``size`` wide."""

    def __init__(
        self, canvas: tk.Canvas, *, size: int, colour: str, at: tuple[int, int]
    ) -> None:
        """Remember where and how large to draw."""
        self._canvas = canvas
        self._size = size
        self._colour = colour
        self._x, self._y = at
        self.width = max(2, round(size / 10))

    def _xy(self, points: tuple[float, ...]) -> list[float]:
        return [
            (self._y if i % 2 else self._x) + value * self._size
            for i, value in enumerate(points)
        ]

    def line(self, *points: float) -> None:
        """A stroke through ``points`` (x0, y0, x1, y1, ...)."""
        self._canvas.create_line(
            *self._xy(points),
            fill=self._colour,
            width=self.width,
            capstyle="round",
            joinstyle="round",
            tags=TAG,
        )

    def oval(self, *box: float, filled: bool = False) -> None:
        """An ellipse in ``box`` (x0, y0, x1, y1), outlined or filled."""
        self._canvas.create_oval(
            *self._xy(box),
            outline=self._colour,
            fill=self._colour if filled else "",
            width=self.width,
            tags=TAG,
        )

    def shape(self, *points: float, filled: bool = False) -> None:
        """A closed polygon through ``points``, outlined or filled."""
        self._canvas.create_polygon(
            *self._xy(points),
            outline=self._colour,
            fill=self._colour if filled else "",
            width=self.width,
            joinstyle="round",
            tags=TAG,
        )

    def arch(self, *box: float) -> None:
        """The top half of the ellipse in ``box`` (a padlock's shackle)."""
        self._canvas.create_arc(
            *self._xy(box),
            start=0,
            extent=180,
            style="arc",
            outline=self._colour,
            width=self.width,
            tags=TAG,
        )


def _check(pen: Pen) -> None:
    pen.line(0.2, 0.55, 0.42, 0.76, 0.82, 0.28)


def _cross(pen: Pen) -> None:
    pen.line(0.25, 0.25, 0.75, 0.75)
    pen.line(0.75, 0.25, 0.25, 0.75)


def _trash(pen: Pen) -> None:
    pen.line(0.18, 0.26, 0.82, 0.26)
    pen.line(0.4, 0.26, 0.42, 0.14, 0.58, 0.14, 0.6, 0.26)
    pen.shape(0.27, 0.34, 0.73, 0.34, 0.68, 0.88, 0.32, 0.88)


def _prev(pen: Pen) -> None:
    pen.line(0.62, 0.22, 0.36, 0.5, 0.62, 0.78)


def _next(pen: Pen) -> None:
    pen.line(0.38, 0.22, 0.64, 0.5, 0.38, 0.78)


def _workout(pen: Pen) -> None:
    pen.line(0.2, 0.5, 0.8, 0.5)
    pen.shape(0.17, 0.28, 0.29, 0.28, 0.29, 0.72, 0.17, 0.72, filled=True)
    pen.shape(0.71, 0.28, 0.83, 0.28, 0.83, 0.72, 0.71, 0.72, filled=True)
    pen.line(0.08, 0.5, 0.17, 0.5)
    pen.line(0.83, 0.5, 0.92, 0.5)


def _leetcode(pen: Pen) -> None:
    pen.line(0.36, 0.28, 0.12, 0.5, 0.36, 0.72)
    pen.line(0.64, 0.28, 0.88, 0.5, 0.64, 0.72)
    pen.line(0.57, 0.2, 0.43, 0.8)


def _book(pen: Pen) -> None:
    pen.shape(0.5, 0.3, 0.1, 0.2, 0.1, 0.76, 0.5, 0.86)
    pen.shape(0.5, 0.3, 0.9, 0.2, 0.9, 0.76, 0.5, 0.86)


def _diet(pen: Pen) -> None:
    pen.oval(0.2, 0.34, 0.8, 0.9, filled=True)
    pen.line(0.5, 0.34, 0.54, 0.14)
    pen.oval(0.56, 0.12, 0.78, 0.26, filled=True)


def _alarm(pen: Pen) -> None:
    pen.oval(0.18, 0.24, 0.82, 0.88)
    pen.line(0.5, 0.38, 0.5, 0.56, 0.63, 0.64)
    pen.oval(0.08, 0.1, 0.3, 0.3, filled=True)
    pen.oval(0.7, 0.1, 0.92, 0.3, filled=True)


def _focus(pen: Pen) -> None:
    pen.oval(0.1, 0.1, 0.9, 0.9)
    pen.oval(0.3, 0.3, 0.7, 0.7)
    pen.oval(0.44, 0.44, 0.56, 0.56, filled=True)


def _padlock(pen: Pen) -> None:
    pen.arch(0.3, 0.12, 0.7, 0.62)
    pen.shape(0.22, 0.44, 0.78, 0.44, 0.78, 0.88, 0.22, 0.88, filled=True)


def _no_entry(pen: Pen) -> None:
    pen.oval(0.14, 0.14, 0.86, 0.86)
    pen.line(0.28, 0.28, 0.72, 0.72)


def _warning(pen: Pen) -> None:
    pen.shape(0.5, 0.12, 0.9, 0.86, 0.1, 0.86)
    pen.line(0.5, 0.38, 0.5, 0.6)
    pen.oval(0.47, 0.71, 0.53, 0.77, filled=True)


def _hourglass(pen: Pen) -> None:
    pen.line(0.22, 0.12, 0.78, 0.12)
    pen.line(0.22, 0.88, 0.78, 0.88)
    pen.shape(0.28, 0.12, 0.72, 0.12, 0.28, 0.88, 0.72, 0.88)


def _sick(pen: Pen) -> None:
    pen.shape(0.15, 0.15, 0.85, 0.15, 0.85, 0.85, 0.15, 0.85, filled=True)


def _normal(pen: Pen) -> None:
    pen.shape(0.15, 0.15, 0.85, 0.15, 0.85, 0.85, 0.15, 0.85)


def _dot(pen: Pen) -> None:
    pen.oval(0.3, 0.3, 0.7, 0.7, filled=True)


def _ring(pen: Pen) -> None:
    pen.oval(0.25, 0.25, 0.75, 0.75)


ICONS: Final[dict[str, Callable[[Pen], None]]] = {
    "check": _check,
    "cross": _cross,
    "trash": _trash,
    "prev": _prev,
    "next": _next,
    "workout": _workout,
    "leetcode": _leetcode,
    "book": _book,
    "diet": _diet,
    "alarm": _alarm,
    "focus": _focus,
    "padlock": _padlock,
    "no_entry": _no_entry,
    "warning": _warning,
    "hourglass": _hourglass,
    "sick": _sick,
    "normal": _normal,
    "dot": _dot,
    "ring": _ring,
}

#: The pictogram each locker is shown as, in place of its name.
LOCKER_ICONS: Final = {
    LOCKER_WORKOUT: "workout",
    LOCKER_LEETCODE: "leetcode",
    LOCKER_BOOK: "book",
    LOCKER_DIET: "diet",
    LOCKER_ALARM: "alarm",
    LOCKER_FOCUS: "focus",
}


def draw(
    canvas: tk.Canvas,
    icon: str,
    *,
    size: int,
    colour: str,
    at: tuple[int, int] = (0, 0),
) -> None:
    """Draw ``icon`` on ``canvas`` in a ``size`` px square whose corner is ``at``."""
    ICONS[icon](Pen(canvas, size=size, colour=colour, at=at))
