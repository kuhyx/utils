# Copyright (c) 2026 Krzysztof Rudnicki
"""The month grid: Monday-first, one button per day, prev/next month chevrons.

The phone's ``DayCalendar``/``DayCell``: a sick day is filled ``cat-2``, a
sick day that keeps a locker carries a dot, Tue-Thu are shaded, and past
days keep their mark but faded and inert. Today stays clickable -- a sick
day can be marked or cleared for today. Deciding what a click *means* stays
with the window; this only reports the date. No words: the month reads
``2026-11`` and the weekday row is dots, with rings on Saturday and Sunday.
"""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING, Final

from sickdays._day import to_iso
from sickdays.gui import _dates
from sickdays.gui import _tokens as tok
from sickdays.gui import _widgets as ui
from sickdays.gui._controls import IconButton, IconSlot

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import date

#: The weekday marks over the grid, in px.
_MARK_PX: Final = 10
#: The keep-a-locker dot inside a sick day's cell, in px.
_DOT_PX: Final = 8


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
        self._first, self._last = _dates.month_bounds(today)
        self.month = today.replace(day=1)
        self._header = tk.Frame(self, name="header", bg=self.cget("bg"))
        self._header.pack(fill="x")
        self._grid = tk.Frame(self, name="days", bg=self.cget("bg"))
        self._grid.pack(pady=(tok.XS, 0))
        self.redraw()

    def step(self, months: int) -> None:
        """Move ``months`` months (within the phone's range) and redraw."""
        target = _dates.shift_month(self.month, months)
        if self._first <= target <= self._last:
            self.month = target
            self.redraw()

    def redraw(self) -> None:
        """Rebuild the header and every day from the current pool."""
        for frame in (self._header, self._grid):
            for child in frame.winfo_children():
                child.destroy()
        self._draw_header()
        for column in range(7):
            mark = "ring" if _dates.is_weekend_column(column) else "dot"
            IconSlot(self._grid, size=_MARK_PX).show(mark, tok.MUTED_ON_DARK).grid(
                row=0, column=column, pady=(0, tok.XS)
            )
        for row, week in enumerate(_dates.month_weeks(self.month), start=1):
            for column, day in enumerate(week):
                if day is not None:
                    self._cell(day).grid(
                        row=row, column=column, padx=tok.XS // 2, pady=tok.XS // 2
                    )

    def _draw_header(self) -> None:
        back = IconButton(self._header, "prev", lambda: self.step(-1), name="prev")
        forward = IconButton(self._header, "next", lambda: self.step(1), name="next")
        back.set_enabled(self.month > self._first)
        forward.set_enabled(self.month < self._last)
        back.pack(side="left")
        forward.pack(side="right")
        ui.label(self._header, _dates.month_title(self.month), "subtitle").pack(
            side="top", pady=tok.XS
        )

    def _cell(self, day: date) -> tk.Button:
        sick = self._is_sick(day)
        past = day < self._today
        fill, text = _cell_colours(sick=sick, past=past, workday=_dates.is_workday(day))
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
            dot = IconSlot(cell, name="dot", size=_DOT_PX).show("dot", text)
            dot.place(relx=1.0, x=-2, y=2, anchor="ne")
        return cell
