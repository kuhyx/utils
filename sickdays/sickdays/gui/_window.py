# Copyright (c) 2026 Krzysztof Rudnicki
"""``sickdays gui``: the desktop picker, the phone's Sick days screen on Tk.

The calendar on the left, :class:`~sickdays.gui.KeepPanel` on the right for
the clicked day, the sick days still ahead underneath (each an ISO date and
the pictograms of the lockers it keeps). The window class is ``sickdays``
(Tk reports ``WM_CLASS "sickdays", "Sickdays"``) so an i3 ``for_window``
rule can float it; ``Escape`` closes it.

No words inside the window (kuhy's textgate rule). The title bar keeps the
app's name: an OS-level app name is a proper noun (textgate settled
decision 4), the same as ``sickdays.desktop``'s ``Name=``.
"""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING, Final

from sickdays._api import is_sick_day, load
from sickdays._day import to_iso, today
from sickdays._keep_api import kept_lockers
from sickdays._model import sick_entries
from sickdays._paths import resolve_paths
from sickdays.gui import _dates
from sickdays.gui import _tokens as tok
from sickdays.gui import _widgets as ui
from sickdays.gui._calendar import MonthCalendar
from sickdays.gui._controls import IconSlot
from sickdays.gui._icons import LOCKER_ICONS
from sickdays.gui._panel import STATUS_ICONS, KeepPanel

if TYPE_CHECKING:
    from datetime import date

    from sickdays._model import SickDay
    from sickdays._paths import Paths

WINDOW_CLASS = "sickdays"
WINDOW_TITLE = "Sick days"
#: A kept locker's pictogram in the list of days ahead, in px.
_KEPT_PX: Final = 16


def saved_icon(entry: SickDay | None) -> str | None:
    """The status mark after the panel closed with ``entry``.

    A check for any write (the grid and the list show what it was); nothing
    when the panel was saved unchanged.
    """
    return None if entry is None else "check"


class SickDaysApp:
    """The whole window, drawn onto ``root``."""

    def __init__(self, root: tk.Tk, *, paths: Paths | None = None) -> None:
        """Style ``root`` and draw the current pool."""
        self._root = root
        self._paths = resolve_paths(paths)
        root.title(WINDOW_TITLE)
        root.configure(bg=tok.INK, padx=tok.LG, pady=tok.LG)
        root.bind("<Escape>", self.close)
        left = tk.Frame(root, bg=tok.INK)
        left.grid(row=0, column=0, sticky="n")
        #: Where the clicked day's panel goes.
        self.host = tk.Frame(root, name="host", bg=tok.INK)
        self.host.grid(row=0, column=1, sticky="n", padx=(tok.LG, 0))
        #: The last outcome's mark: a check, or the panel's refusal icons.
        self.status = IconSlot(left, name="status")
        self.status.pack(anchor="w")
        log = self._paths.log
        self.calendar = MonthCalendar(
            left,
            today=today(),
            is_sick=lambda day: is_sick_day(day, log_path=log),
            has_dot=lambda day: bool(kept_lockers(day, log_path=log)),
            on_day=self.select,
        )
        self.calendar.pack(anchor="w", pady=(tok.SM, 0))
        IconSlot(left, name="ahead").show("sick", tok.SICK).pack(
            anchor="w", pady=(tok.LG, tok.SM)
        )
        self._list = tk.Frame(left, name="upcoming", bg=tok.INK)
        self._list.pack(anchor="w", fill="x")
        self._draw_upcoming()

    def close(self, _event: object = None) -> None:
        """Close the window (bound to ``Escape``)."""
        self._root.destroy()

    def select(self, day: date) -> None:
        """Open the panel for ``day``, or refuse a free day in the status mark."""
        self._close_panel()
        if not is_sick_day(day, log_path=self._paths.log):
            block = _dates.free_day_block(day)
            if block is not None:
                self.status.show(*STATUS_ICONS[block])
                return
        self.status.show(None)
        KeepPanel(
            self.host,
            day,
            on_saved=self._saved,
            on_cancel=self._close_panel,
            paths=self._paths,
        ).pack(anchor="n")

    def _saved(self, entry: SickDay | None) -> None:
        self._close_panel()
        self.status.show(saved_icon(entry), tok.SUCCESS)
        self.calendar.redraw()
        self._draw_upcoming()

    def _close_panel(self) -> None:
        for child in self.host.winfo_children():
            child.destroy()

    def _draw_upcoming(self) -> None:
        for child in self._list.winfo_children():
            child.destroy()
        reference = today()
        for entry in sick_entries(load(self._paths.log)):
            if entry.day < reference:
                continue
            row = tk.Frame(self._list, name=f"day-{to_iso(entry.day)}", bg=tok.INK)
            row.pack(anchor="w", pady=(0, tok.XS))
            ui.label(row, to_iso(entry.day), "body").pack(side="left")
            for locker in _dates.kept_in_order(entry.keep):
                IconSlot(row, name=f"kept-{locker}", size=_KEPT_PX).show(
                    LOCKER_ICONS[locker], tok.MUTED_ON_DARK
                ).pack(side="left", padx=(tok.SM, 0))


def run(*, paths: Paths | None = None) -> int:
    """Open the window and block until it is closed."""
    root = tk.Tk(className=WINDOW_CLASS)
    SickDaysApp(root, paths=paths)
    root.mainloop()
    return 0
