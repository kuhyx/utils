# Copyright (c) 2026 Krzysztof Rudnicki
"""The month grid: Monday-first, one button per day, prev/next month arrows.

The phone's ``DayCalendar``/``DayCell``: a sick day is filled ``cat-2``, a
sick day that keeps a locker carries a dot, Tue-Thu are shaded, and past
days keep their mark but faded and inert. Today stays clickable -- a sick
day can be marked or cleared for today. Deciding what a click *means* stays
with the window; this only reports the date.
"""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING

from sickdays._day import to_iso
from sickdays.gui import _text
from sickdays.gui import _tokens as tok
from sickdays.gui import _widgets as ui

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import date

_PREV = "\N{SINGLE LEFT-POINTING ANGLE QUOTATION MARK}"
_NEXT = "\N{SINGLE RIGHT-POINTING ANGLE QUOTATION MARK}"


def _cell_colours(*, sick: bool, past: bool, workday: bool) -> tuple[str, str]:
    """(fill, text) for one day, faded when past, as ``DayCell`` draws it."""
    if sick:
        fill = tok.blend(tok.SICK, tok.INK, tok.PAST_ALPHA) if past else tok.SICK
        return fill, tok.ON_FILL
    fill = tok.INK_RAISED_1 if workday else tok.INK
    text = (
        tok.blend(tok.TEXT_ON_DARK, fill, tok.PAST_ALPHA) if past else tok.TEXT_ON_DARK
    )
    return fill, text


class MonthCalendar(tk.Frame):
    """One month of one pool; :meth:`redraw` repaints it from the callbacks."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        today: date,
        is_sick: Callable[[date], bool],
        has_dot: Callable[[date], bool],
        on_day: Callable[[date], None],
    ) -> None:
        """Show the month holding ``today``."""
        super().__init__(parent, bg=parent.cget("bg"))
        self._today = today
        self._is_sick = is_sick
        self._has_dot = has_dot
        self._on_day = on_day
        self._first, self._last = _text.month_bounds(today)
        self.month = today.replace(day=1)
        self._header = tk.Frame(self, name="header", bg=self.cget("bg"))
        self._header.pack(fill="x")
        self._grid = tk.Frame(self, name="days", bg=self.cget("bg"))
        self._grid.pack(pady=(tok.XS, 0))
        self.redraw()

    def step(self, months: int) -> None:
        """Move ``months`` months (within the phone's range) and redraw."""
        target = _text.shift_month(self.month, months)
        if self._first <= target <= self._last:
            self.month = target
            self.redraw()

    def redraw(self) -> None:
        """Rebuild the header and every day from the current pool."""
        for frame in (self._header, self._grid):
            for child in frame.winfo_children():
                child.destroy()
        self._draw_header()
        for column, initial in enumerate(_text.WEEKDAY_INITIALS):
            ui.label(self._grid, initial, "caption", fg=tok.MUTED_ON_DARK).grid(
                row=0, column=column
            )
        for row, week in enumerate(_text.month_weeks(self.month), start=1):
            for column, day in enumerate(week):
                if day is not None:
                    self._cell(day).grid(
                        row=row, column=column, padx=tok.XS // 2, pady=tok.XS // 2
                    )

    def _draw_header(self) -> None:
        back = ui.button(self._header, _PREV, lambda: self.step(-1), name="prev")
        forward = ui.button(self._header, _NEXT, lambda: self.step(1), name="next")
        back.configure(state="normal" if self.month > self._first else "disabled")
        forward.configure(state="normal" if self.month < self._last else "disabled")
        back.pack(side="left")
        forward.pack(side="right")
        ui.label(self._header, _text.month_title(self.month), "subtitle").pack(
            side="top", pady=tok.XS
        )

    def _cell(self, day: date) -> tk.Button:
        sick = self._is_sick(day)
        past = day < self._today
        fill, text = _cell_colours(sick=sick, past=past, workday=_text.is_workday(day))
        cell = tk.Button(
            self._grid,
            name=f"day-{to_iso(day)}",
            text=str(day.day),
            command=lambda: self._on_day(day),
            state="disabled" if past else "normal",
            bg=fill,
            fg=text,
            activebackground=fill,
            activeforeground=text,
            disabledforeground=text,
            font=tok.font(ui.family(self), "body", bold=sick),
            width=3,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            padx=tok.SM,
            pady=tok.SM,
            cursor="arrow" if past else "hand2",
        )
        if sick and self._has_dot(day):
            dot = tk.Label(cell, name="dot", text="●", fg=text, bg=fill)
            dot.configure(font=tok.font(ui.family(self), "caption"), padx=0, pady=0)
            dot.place(relx=1.0, x=-2, y=0, anchor="ne")
        return cell
