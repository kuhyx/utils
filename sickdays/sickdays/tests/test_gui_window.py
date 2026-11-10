# Copyright (c) 2026 Krzysztof Rudnicki
"""The picker window and its month grid, against a real (unmapped) Tk."""

from __future__ import annotations

from datetime import date, timedelta
import tkinter as tk
from typing import TYPE_CHECKING

from sickdays._api import add_sick_day
from sickdays._day import to_iso, today
from sickdays._model import SickDay
from sickdays.gui import KeepPanel, SickDaysApp, _dates, _window
from sickdays.gui import _tokens as tok
from sickdays.gui._controls import IconButton, IconSlot

if TYPE_CHECKING:
    import pytest

FUTURE = today() + timedelta(days=3)


def _upcoming(app: SickDaysApp) -> dict[str, list[str]]:
    """Each listed day's ISO date -> the locker icons it keeps."""
    rows = app.calendar.master.nametowidget("upcoming").winfo_children()
    listed: dict[str, list[str]] = {}
    for row in rows:
        icons = [
            str(slot.icon)
            for slot in row.winfo_children()
            if isinstance(slot, IconSlot)
        ]
        (date_label,) = [c for c in row.winfo_children() if isinstance(c, tk.Label)]
        listed[str(date_label.cget("text"))] = icons
    return listed


def _cell(app: SickDaysApp, day: date) -> tk.Button:
    widget = app.calendar.nametowidget(f"days.day-{to_iso(day)}")
    assert isinstance(widget, tk.Button)
    return widget


def _panel(app: SickDaysApp) -> KeepPanel:
    (panel,) = app.host.winfo_children()
    assert isinstance(panel, KeepPanel)
    return panel


def test_an_empty_pool_lists_nothing_ahead(tk_root: tk.Tk) -> None:
    app = SickDaysApp(tk_root)
    assert tk_root.title() == "Sick days"
    assert _upcoming(app) == {}
    assert app.status.icon is None
    assert app.host.winfo_children() == []


def test_mark_a_day_from_the_calendar(tk_root: tk.Tk) -> None:
    later = FUTURE + timedelta(days=1)
    add_sick_day(later)
    app = SickDaysApp(tk_root)
    app.calendar.month = FUTURE.replace(day=1)
    app.calendar.redraw()
    _cell(app, FUTURE).invoke()
    panel = _panel(app)
    panel.nametowidget("keep-leetcode").invoke()
    panel.nametowidget("actions.mark").invoke()
    assert panel.sync_thread is not None
    panel.sync_thread.join(timeout=5)
    assert app.host.winfo_children() == []
    assert app.status.icon == "check"
    assert _upcoming(app) == {to_iso(FUTURE): ["leetcode"], to_iso(later): []}
    cell = _cell(app, FUTURE)
    assert str(cell.cget("bg")).upper() == tok.SICK
    assert cell.nametowidget("dot").winfo_exists()


def test_cancel_closes_the_panel(tk_root: tk.Tk) -> None:
    app = SickDaysApp(tk_root)
    app.select(FUTURE)
    _panel(app).nametowidget("actions.cancel").invoke()
    assert app.host.winfo_children() == []


def test_a_free_day_is_refused_before_the_panel_opens(
    tk_root: tk.Tk, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "sickdays.gui._dates.free_day_predicate", lambda: lambda _d: True
    )
    app = SickDaysApp(tk_root)
    app.select(FUTURE)
    assert app.host.winfo_children() == []
    assert app.status.icon == "no_entry"


def test_a_sick_day_on_a_free_day_still_opens(
    tk_root: tk.Tk, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_sick_day(FUTURE)
    monkeypatch.setattr(
        "sickdays.gui._dates.free_day_predicate", lambda: lambda _d: True
    )
    app = SickDaysApp(tk_root)
    app.select(FUTURE)
    assert _panel(app).nametowidget("actions.clear").winfo_exists()


def test_the_list_shows_upcoming_days_with_kept_lockers(tk_root: tk.Tk) -> None:
    add_sick_day(FUTURE, keep=["alarm", "workout"])
    add_sick_day(FUTURE + timedelta(days=1))
    past = today() - timedelta(days=1)
    add_sick_day(past, now=past)
    assert _upcoming(SickDaysApp(tk_root)) == {
        to_iso(FUTURE): ["workout", "alarm"],
        to_iso(FUTURE + timedelta(days=1)): [],
    }


def test_saved_icon() -> None:
    assert _window.saved_icon(None) is None
    assert _window.saved_icon(SickDay(FUTURE, is_sick=True)) == "check"
    assert _window.saved_icon(SickDay(FUTURE, is_sick=False)) == "check"


def test_the_month_reads_as_numerals_with_weekday_marks(tk_root: tk.Tk) -> None:
    app = SickDaysApp(tk_root)
    title = app.calendar.nametowidget("header").winfo_children()[-1]
    assert isinstance(title, tk.Label)
    assert title.cget("text") == _dates.month_title(today().replace(day=1))
    marks = [
        child.icon
        for child in app.calendar.nametowidget("days").winfo_children()
        if isinstance(child, IconSlot)
    ]
    assert marks == ["dot"] * 5 + ["ring"] * 2


def test_past_days_are_inert_and_faded(tk_root: tk.Tk) -> None:
    app = SickDaysApp(tk_root)
    first = today().replace(day=1)
    app.calendar.month = first - timedelta(days=1)
    app.calendar.redraw()
    cell = _cell(app, app.calendar.month.replace(day=1))
    assert str(cell.cget("state")) == "disabled"


def test_month_arrows_stop_at_the_phones_range(tk_root: tk.Tk) -> None:
    app = SickDaysApp(tk_root)
    first, last = _dates.month_bounds(today())
    for _ in range(30):
        app.calendar.step(1)
    assert app.calendar.month == last
    for _ in range(30):
        app.calendar.step(-1)
    assert app.calendar.month == first
    back = app.calendar.nametowidget("header.prev")
    assert isinstance(back, IconButton)
    assert back.icon == "prev"
    assert str(back.cget("state")) == "disabled"


def test_escape_closes_the_window(monkeypatch: pytest.MonkeyPatch) -> None:
    closed: list[bool] = []
    root = tk.Tk(className="sickdays-test")
    root.withdraw()
    app = SickDaysApp(root)
    assert root.bind("<Escape>")
    real_destroy = root.destroy
    monkeypatch.setattr(root, "destroy", lambda: closed.append(True))
    app.close()
    assert closed == [True]
    real_destroy()


def test_run_opens_the_window_and_blocks(
    tk_root: tk.Tk, monkeypatch: pytest.MonkeyPatch
) -> None:
    classes: list[str] = []

    def make_root(**options: str) -> tk.Tk:
        classes.append(options["className"])
        return tk_root

    monkeypatch.setattr(tk, "Tk", make_root)
    monkeypatch.setattr(tk_root, "mainloop", lambda: None)
    assert _window.run() == 0
    assert classes == ["sickdays"]
