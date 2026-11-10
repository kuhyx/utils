# Copyright (c) 2026 Krzysztof Rudnicki
"""KeepPanel: a switch per locker for one day, and the buttons that write them.

The embeddable half of the picker. It is a plain ``tk.Frame``: no root, no
mainloop, no ``bind_all``, no grab, no focus stealing and no ``wm_*`` call,
so screen-locker can drop it onto its fullscreen surface in-process, under
its own X grab (a separate window could not get input there).

On is "this locker still applies", off is "stands down", all off by default
-- the phone's ``SickDaySheet``. A normal day offers "mark sick" (check); a
sick day offers "save" (check, a keep-only edit) and "clear" (red bin). A
past day (padlock), a free day (no-entry sign) or a free-day pool that cannot
be checked (warning) shows its icon and offers no write. A refused write is
shown in the panel as an icon, never raised: an exception in a Tk callback
only reaches stderr, which nobody sees under a lock. The panel shows no
words (kuhy's textgate rule): a locker is its pictogram, the day its ISO date.
"""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from typing import TYPE_CHECKING, Final

from sickdays._api import add_sick_day, is_sick_day, remove_sick_day
from sickdays._constants import LOCKERS
from sickdays._day import to_iso, today
from sickdays._errors import SickDayError
from sickdays._keep_api import kept_lockers, set_kept_lockers
from sickdays._paths import resolve_paths
from sickdays._sync import sync_quietly
from sickdays.gui import _dates
from sickdays.gui import _tokens as tok
from sickdays.gui import _widgets as ui
from sickdays.gui._controls import IconButton, IconSlot, Toggle
from sickdays.gui._icons import LOCKER_ICONS

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import date

    from sickdays._model import SickDay
    from sickdays._paths import Paths


_LOG = logging.getLogger(__name__)

#: (icon, colour) for each reason the panel shows, keyed by that reason.
STATUS_ICONS: Final = {
    "past": ("padlock", tok.MUTED_ON_DARK),
    "free": ("no_entry", tok.DANGER),
    "unavailable": ("warning", tok.DANGER),
    "refused": ("warning", tok.DANGER),
    "busy": ("hourglass", tok.DANGER),
}

#: Held by every background sync, and tried by every write. ``sync()`` reads
#: the pool, waits on the network, then writes its merged copy back, so a
#: write landing in between would be silently overwritten. A write that finds
#: a sync running is refused ("try again") rather than lost.
_SYNC_LOCK = threading.Lock()


def _serialised_sync(paths: Paths) -> None:
    with _SYNC_LOCK:
        sync_quietly(paths=paths)


def start_sync(paths: Paths) -> threading.Thread:
    """Push the write in the background so the phone sees it; never raises.

    Not a daemon: a window closed right after "Mark sick" must not kill the
    push half-way. The thread touches no widget.
    """
    thread = threading.Thread(
        target=_serialised_sync,
        args=(paths,),
        name="sickdays-sync",
        daemon=False,
    )
    thread.start()
    return thread


class KeepPanel(tk.Frame):
    """Mark ``day`` sick with some lockers kept, or edit / clear a sick day.

    ``on_saved`` is called once per successful click, after the write and
    after the background sync has started:

    * ``actions.mark`` -> the new :class:`~sickdays.SickDay` (``is_sick=True``);
    * ``actions.save`` with a changed set -> the stored entry (``is_sick=True``);
    * ``actions.save`` with nothing changed -> ``None``: nothing written, no sync;
    * ``actions.clear`` -> the cleared entry (``is_sick=False``).

    A refused write (:class:`~sickdays.SickDayError`, or a click while the
    previous write's sync is still running) is shown in the panel's
    ``status`` slot and ``on_saved`` is not called; :attr:`reason` names it
    (a :data:`STATUS_ICONS` key). ``on_cancel``, when given, adds an
    ``actions.cancel`` cross that calls it. The panel never destroys itself;
    the callbacks decide what happens to it.
    """

    def __init__(
        self,
        parent: tk.Misc,
        day: date,
        *,
        on_saved: Callable[[SickDay | None], None],
        on_cancel: Callable[[], None] | None = None,
        paths: Paths | None = None,
    ) -> None:
        """Read ``day``'s current state from the pool and draw the panel."""
        super().__init__(parent, bg=tok.INK_RAISED_1, padx=tok.MD, pady=tok.MD)
        self._day = day
        self._paths = resolve_paths(paths)
        self._on_saved = on_saved
        self._sick = is_sick_day(day, log_path=self._paths.log)
        self._kept = kept_lockers(day, log_path=self._paths.log)
        self._vars = {
            locker: tk.BooleanVar(self, value=locker in self._kept)
            for locker in LOCKERS
        }
        #: The last background sync, for callers (and tests) that wait on it.
        self.sync_thread: threading.Thread | None = None
        #: Why the panel refuses, a :data:`STATUS_ICONS` key, or ``None``.
        self.reason: str | None = None
        blocked = self._blocked_reason()
        self._draw_switches(editable=blocked is None)
        self._status = IconSlot(self, name="status")
        self._status.grid(
            row=len(LOCKERS) + 1, column=0, columnspan=2, sticky="w", pady=(tok.SM, 0)
        )
        self._show(blocked)
        self._draw_actions(writable=blocked is None, on_cancel=on_cancel)

    def kept(self) -> frozenset[str]:
        """The lockers currently switched on."""
        return frozenset(locker for locker, var in self._vars.items() if var.get())

    def _blocked_reason(self) -> str | None:
        if self._day < today():
            return "past"
        return None if self._sick else _dates.free_day_block(self._day)

    def _show(self, reason: str | None) -> None:
        self.reason = reason
        if reason is None:
            self._status.show(None)
            return
        icon, colour = STATUS_ICONS[reason]
        self._status.show(icon, colour)

    def _draw_switches(self, *, editable: bool) -> None:
        head = tk.Frame(self, name="head", bg=self.cget("bg"))
        head.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, tok.SM))
        IconSlot(head, name="state").show(
            "sick" if self._sick else "normal", tok.SICK
        ).pack(side="left", padx=(0, tok.SM))
        ui.label(head, to_iso(self._day), "subtitle", name="title").pack(side="left")
        for row, locker in enumerate(LOCKERS, start=1):
            IconSlot(self, name=f"icon-{locker}").show(LOCKER_ICONS[locker]).grid(
                row=row, column=0, sticky="w", pady=tok.XS
            )
            switch = Toggle(self, self._vars[locker], name=f"keep-{locker}")
            switch.grid(row=row, column=1, sticky="e", padx=(tok.LG, 0), pady=tok.XS)
            if not editable:
                switch.set_enabled(False)

    def _draw_actions(
        self, *, writable: bool, on_cancel: Callable[[], None] | None
    ) -> None:
        actions = tk.Frame(self, name="actions", bg=self.cget("bg"))
        actions.grid(
            row=len(LOCKERS) + 2, column=0, columnspan=2, sticky="we", pady=(tok.MD, 0)
        )
        buttons: list[IconButton] = []
        if writable and self._sick:
            buttons.append(
                IconButton(actions, "check", self._save, kind="primary", name="save")
            )
            buttons.append(
                IconButton(actions, "trash", self._clear, kind="danger", name="clear")
            )
        elif writable:
            buttons.append(
                IconButton(actions, "check", self._mark, kind="primary", name="mark")
            )
        if on_cancel is not None:
            buttons.append(IconButton(actions, "cross", on_cancel, name="cancel"))
        for button in buttons:
            button.pack(side="left", padx=(0, tok.SM))

    def _mark(self) -> None:
        self._write(
            lambda: add_sick_day(self._day, keep=self.kept(), paths=self._paths)
        )

    def _save(self) -> None:
        keep = self.kept()
        if keep == self._kept:
            # A fresh tick on an unchanged set would only churn the sync.
            self._on_saved(None)
            return
        self._write(lambda: set_kept_lockers(self._day, keep, paths=self._paths))

    def _clear(self) -> None:
        self._write(lambda: remove_sick_day(self._day, paths=self._paths))

    def _write(self, action: Callable[[], SickDay]) -> None:
        # Non-blocking on purpose (no ``with``): waiting would freeze Tk for
        # the whole network round trip.
        if not _SYNC_LOCK.acquire(blocking=False):  # pylint: disable=consider-using-with
            self._show("busy")
            return
        try:
            entry = action()
        except SickDayError as exc:
            _LOG.warning("sick-day write refused: %s", exc)
            self._show("refused")
            return
        finally:
            _SYNC_LOCK.release()
        self.sync_thread = start_sync(self._paths)
        # Last: the callback may destroy this panel.
        self._on_saved(entry)
