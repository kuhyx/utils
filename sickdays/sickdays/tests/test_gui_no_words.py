# Copyright (c) 2026 Krzysztof Rudnicki
"""The textgate guard: no letter on any widget of the picker, in any state.

Everything this window shows is chrome except numerals and ISO dates (day
numbers, ``2026-11``, ``2026-11-13``), so the guard bans every letter, not
just words. The window title is the app's proper noun (textgate settled
decision 4) and is checked on its own.
"""

from __future__ import annotations

from datetime import timedelta
import re
import tkinter as tk
from typing import TYPE_CHECKING

from sickdays._api import add_sick_day
from sickdays._day import today
from sickdays._errors import ConflictCheckUnavailableError
from sickdays.gui import KeepPanel, SickDaysApp, _panel

if TYPE_CHECKING:
    import pytest

FUTURE = today() + timedelta(days=3)
LETTER = re.compile(r"[^\W\d_]")


def _shown(widget: tk.Misc) -> list[str]:
    """Every string ``widget`` and its descendants paint."""
    found: list[str] = []
    for child in widget.winfo_children():
        if isinstance(child, tk.Canvas):
            # Raw Tcl: typeshed types Canvas.type()/itemcget() too loosely.
            path = str(child)
            found.extend(
                str(child.tk.call(path, "itemcget", item, "-text"))
                for item in child.find_all()
                if str(child.tk.call(path, "type", item)) == "text"
            )
        elif isinstance(child, (tk.Label, tk.Button, tk.Checkbutton)):
            found.append(str(child.cget("text")))
        found.extend(_shown(child))
    return found


def _assert_no_letters(widget: tk.Misc) -> None:
    shown = _shown(widget)
    assert shown, "the guard walked no widget"
    worded = [text for text in shown if LETTER.search(text)]
    assert worded == []


def test_the_window_title_is_the_app_name(tk_root: tk.Tk) -> None:
    SickDaysApp(tk_root)
    assert tk_root.title() == "Sick days"


def test_the_window_shows_no_letters(tk_root: tk.Tk) -> None:
    add_sick_day(FUTURE, keep=["alarm", "workout"])
    app = SickDaysApp(tk_root)
    _assert_no_letters(tk_root)
    app.select(FUTURE + timedelta(days=1))
    _assert_no_letters(tk_root)


def test_the_window_after_a_refusal_shows_no_letters(
    tk_root: tk.Tk, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "sickdays.gui._dates.free_day_predicate", lambda: lambda _d: True
    )
    SickDaysApp(tk_root).select(FUTURE)
    _assert_no_letters(tk_root)


def test_the_window_after_a_save_shows_no_letters(tk_root: tk.Tk) -> None:
    app = SickDaysApp(tk_root)
    app.select(FUTURE)
    (panel,) = app.host.winfo_children()
    panel.nametowidget("actions.mark").invoke()
    assert isinstance(panel, KeepPanel)
    assert panel.sync_thread is not None
    panel.sync_thread.join(timeout=5)
    _assert_no_letters(tk_root)


def test_every_panel_state_shows_no_letters(
    tk_root: tk.Tk, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_sick_day(FUTURE, keep=["book"])
    for day in (FUTURE, FUTURE + timedelta(days=1), today() - timedelta(days=1)):
        _assert_no_letters(
            KeepPanel(tk_root, day, on_saved=lambda _e: None, on_cancel=lambda: None)
        )

    def unavailable() -> None:
        msg = "cannot check the free-day pool"
        raise ConflictCheckUnavailableError(msg)

    monkeypatch.setattr("sickdays.gui._dates.free_day_predicate", unavailable)
    _assert_no_letters(KeepPanel(tk_root, FUTURE + timedelta(days=2), on_saved=print))


def test_a_refused_or_busy_write_shows_no_letters(tk_root: tk.Tk) -> None:
    refused = KeepPanel(tk_root, FUTURE + timedelta(days=4), on_saved=print)
    add_sick_day(FUTURE + timedelta(days=4))
    refused.nametowidget("actions.mark").invoke()
    _assert_no_letters(refused)
    busy = KeepPanel(tk_root, FUTURE + timedelta(days=5), on_saved=print)
    with _panel._SYNC_LOCK:
        busy.nametowidget("actions.mark").invoke()
    _assert_no_letters(busy)
