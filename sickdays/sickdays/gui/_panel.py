# Copyright (c) 2026 Krzysztof Rudnicki
"""KeepPanel: the five switches for one day, and the buttons that write them.

The embeddable half of the picker. It is a plain ``tk.Frame``: no root, no
mainloop, no ``bind_all``, no grab, no focus stealing and no ``wm_*`` call,
so screen-locker can drop it onto its fullscreen surface in-process, under
its own X grab (a separate window could not get input there).

On is "this locker still applies", off is "stands down", all off by default
-- the phone's ``SickDaySheet``. A normal day offers "Mark sick"; a sick day
offers "Save" (a keep-only edit) and "Clear sick day". A past day, a free
day, or a free-day pool that cannot be checked shows why and offers no
write. A refused write is shown in the panel, never raised: an exception in a
Tk callback only reaches stderr, which nobody sees under a lock.
"""

from __future__ import annotations

import threading
import tkinter as tk
from typing import TYPE_CHECKING

from sickdays._api import add_sick_day, is_sick_day, remove_sick_day
from sickdays._constants import LOCKERS
from sickdays._day import today
from sickdays._errors import SickDayError
from sickdays._keep_api import kept_lockers, set_kept_lockers
from sickdays._paths import resolve_paths
from sickdays._sync import sync_quietly
from sickdays.gui import _text
from sickdays.gui import _tokens as tok
from sickdays.gui import _widgets as ui

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import date

    from sickdays._model import SickDay
    from sickdays._paths import Paths


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

    * "Mark sick" -> the new :class:`~sickdays.SickDay` (``is_sick=True``);
    * "Save" with a changed set -> the stored entry (``is_sick=True``);
    * "Save" with nothing changed -> ``None``: nothing written, no sync;
    * "Clear sick day" -> the cleared entry (``is_sick=False``).

    A refused write (:class:`~sickdays.SickDayError`, or a click while the
    previous write's sync is still running) is shown in the panel and
    ``on_saved`` is not called. ``on_cancel``, when given, adds a
    "Cancel" button that calls it. The panel never destroys itself; the
    callbacks decide what happens to it.
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
        blocked = self._blocked_reason()
        self._draw_switches(editable=blocked is None)
        self._status = ui.label(
            self, blocked or "", "label", fg=tok.DANGER, name="status"
        )
        self._status.grid(row=len(LOCKERS) + 2, column=0, columnspan=2, sticky="w")
        self._draw_actions(writable=blocked is None, on_cancel=on_cancel)

    def kept(self) -> frozenset[str]:
        """The lockers currently switched on."""
        return frozenset(locker for locker, var in self._vars.items() if var.get())

    def _blocked_reason(self) -> str | None:
        if self._day < today():
            return _text.PAST_NOTE
        return None if self._sick else _text.free_day_refusal(self._day)

    def _draw_switches(self, *, editable: bool) -> None:
        title = _text.panel_title(self._day, sick=self._sick)
        ui.label(self, title, "subtitle", name="title").grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ui.label(self, _text.SHEET_HELP, "caption", fg=tok.MUTED_ON_DARK).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(tok.XS, tok.SM)
        )
        for row, locker in enumerate(LOCKERS, start=2):
            ui.label(self, _text.LOCKER_LABELS[locker], "body").grid(
                row=row, column=0, sticky="w", pady=tok.XS
            )
            switch = ui.toggle(self, self._vars[locker], name=f"keep-{locker}")
            switch.grid(row=row, column=1, sticky="e", padx=(tok.LG, 0), pady=tok.XS)
            if not editable:
                switch.configure(state="disabled")

    def _draw_actions(
        self, *, writable: bool, on_cancel: Callable[[], None] | None
    ) -> None:
        actions = tk.Frame(self, name="actions", bg=self.cget("bg"))
        actions.grid(
            row=len(LOCKERS) + 3, column=0, columnspan=2, sticky="we", pady=(tok.MD, 0)
        )
        buttons: list[tk.Button] = []
        if writable and self._sick:
            buttons.append(
                ui.button(actions, "Save", self._save, kind="primary", name="save")
            )
            buttons.append(
                ui.button(
                    actions, "Clear sick day", self._clear, kind="danger", name="clear"
                )
            )
        elif writable:
            buttons.append(
                ui.button(actions, "Mark sick", self._mark, kind="primary", name="mark")
            )
        if on_cancel is not None:
            buttons.append(ui.button(actions, "Cancel", on_cancel, name="cancel"))
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
            self._status.configure(text=_text.BUSY_NOTE, fg=tok.DANGER)
            return
        try:
            entry = action()
        except SickDayError as exc:
            self._status.configure(text=str(exc), fg=tok.DANGER)
            return
        finally:
            _SYNC_LOCK.release()
        self.sync_thread = start_sync(self._paths)
        # Last: the callback may destroy this panel.
        self._on_saved(entry)
