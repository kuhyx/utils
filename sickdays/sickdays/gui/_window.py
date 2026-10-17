# Copyright (c) 2026 Krzysztof Rudnicki
"""``sickdays gui``: the desktop picker, the phone's Sick days screen on Tk.

The calendar on the left, :class:`~sickdays.gui.KeepPanel` on the right for
the clicked day, the sick days still ahead underneath. The window class is
``sickdays`` (Tk reports ``WM_CLASS "sickdays", "Sickdays"``) so an i3
``for_window`` rule can float it; ``Escape`` closes it.
"""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING

from sickdays._api import is_sick_day, load
from sickdays._day import today
from sickdays._keep_api import kept_lockers
from sickdays._model import sick_entries
from sickdays._paths import resolve_paths
from sickdays.gui import _text
from sickdays.gui import _tokens as tok
from sickdays.gui import _widgets as ui
from sickdays.gui._calendar import MonthCalendar
from sickdays.gui._panel import KeepPanel

if TYPE_CHECKING:
    from datetime import date

    from sickdays._model import SickDay
    from sickdays._paths import Paths

WINDOW_CLASS = "sickdays"


def saved_message(entry: SickDay | None, day: date) -> str:
    """The status line after the panel closed with ``entry``."""
    label = _text.day_label(day)
    if entry is None:
        return f"{label}: nothing changed"
    if not entry.is_sick:
        return f"{label} is a normal day again"
    kept = _text.kept_label(entry.keep)
    return f"{label} is a sick day — " + (
        f"kept: {kept}" if kept else "every locker stands down"
    )


class SickDaysApp:
    """The whole window, drawn onto ``root``."""

    def __init__(self, root: tk.Tk, *, paths: Paths | None = None) -> None:
        """Style ``root`` and draw the current pool."""
        self._root = root
        self._paths = resolve_paths(paths)
        root.title("Sick days")
        root.configure(bg=tok.INK, padx=tok.LG, pady=tok.LG)
        root.bind("<Escape>", self.close)
        left = tk.Frame(root, bg=tok.INK)
        left.grid(row=0, column=0, sticky="n")
        #: Where the clicked day's panel goes.
        self.host = tk.Frame(root, name="host", bg=tok.INK)
        self.host.grid(row=0, column=1, sticky="n", padx=(tok.LG, 0))
        ui.label(left, "Sick days", "title").pack(anchor="w")
        ui.label(left, _text.INTRO, "body").pack(anchor="w", pady=(tok.SM, 0))
        ui.label(left, _text.INTRO_DETAIL, "caption", fg=tok.MUTED_ON_DARK).pack(
            anchor="w", pady=(tok.SM, 0)
        )
        self.status = ui.label(left, "", "label", name="status")
        self.status.pack(anchor="w", pady=(tok.SM, 0))
        log = self._paths.log
        self.calendar = MonthCalendar(
            left,
            today=today(),
            is_sick=lambda day: is_sick_day(day, log_path=log),
            has_dot=lambda day: bool(kept_lockers(day, log_path=log)),
            on_day=self.select,
        )
        self.calendar.pack(anchor="w", pady=(tok.MD, 0))
        ui.label(left, "Marked sick", "subtitle").pack(
            anchor="w", pady=(tok.LG, tok.SM)
        )
        self._list = tk.Frame(left, name="upcoming", bg=tok.INK)
        self._list.pack(anchor="w", fill="x")
        self._draw_upcoming()

    def close(self, _event: object = None) -> None:
        """Close the window (bound to ``Escape``)."""
        self._root.destroy()

    def select(self, day: date) -> None:
        """Open the panel for ``day``, or refuse a free day in the status line."""
        self._close_panel()
        if not is_sick_day(day, log_path=self._paths.log):
            refusal = _text.free_day_refusal(day)
            if refusal is not None:
                self._set_status(refusal, failed=True)
                return
        self._set_status("", failed=False)
        KeepPanel(
            self.host,
            day,
            on_saved=lambda entry: self._saved(entry, day),
            on_cancel=self._close_panel,
            paths=self._paths,
        ).pack(anchor="n")

    def _saved(self, entry: SickDay | None, day: date) -> None:
        self._close_panel()
        self._set_status(saved_message(entry, day), failed=False)
        self.calendar.redraw()
        self._draw_upcoming()

    def _close_panel(self) -> None:
        for child in self.host.winfo_children():
            child.destroy()

    def _set_status(self, text: str, *, failed: bool) -> None:
        self.status.configure(text=text, fg=tok.DANGER if failed else tok.SUCCESS)

    def _draw_upcoming(self) -> None:
        for child in self._list.winfo_children():
            child.destroy()
        reference = today()
        upcoming = [
            entry
            for entry in sick_entries(load(self._paths.log))
            if entry.day >= reference
        ]
        if not upcoming:
            ui.label(self._list, _text.NONE_AHEAD, "body", fg=tok.MUTED_ON_DARK).pack(
                anchor="w"
            )
        for entry in upcoming:
            ui.label(self._list, _text.day_label(entry.day), "body").pack(anchor="w")
            kept = _text.kept_label(entry.keep)
            if kept:
                ui.label(
                    self._list, f"Kept: {kept}", "label", fg=tok.MUTED_ON_DARK
                ).pack(anchor="w", pady=(0, tok.XS))


def run(*, paths: Paths | None = None) -> int:
    """Open the window and block until it is closed."""
    root = tk.Tk(className=WINDOW_CLASS)
    SickDaysApp(root, paths=paths)
    root.mainloop()
    return 0
