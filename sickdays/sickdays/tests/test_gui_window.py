# Copyright (c) 2026 Krzysztof Rudnicki
"""The picker window and its month grid, against a real (unmapped) Tk."""

from __future__ import annotations

from datetime import date, timedelta
import tkinter as tk
from typing import TYPE_CHECKING

from sickdays._api import add_sick_day
from sickdays._day import to_iso, today
from sickdays._model import SickDay
from sickdays.gui import KeepPanel, SickDaysApp, _text, _window
from sickdays.gui import _tokens as tok

if TYPE_CHECKING:
    import pytest

FUTURE = today() + timedelta(days=3)


def _texts(widget: tk.Misc) -> list[str]:
    found: list[str] = []
    for child in widget.winfo_children():
        if isinstance(child, tk.Label):
            found.append(str(child.cget("text")))
        found.extend(_texts(child))
    return found


def _cell(app: SickDaysApp, day: date) -> tk.Button:
    widget = app.calendar.nametowidget(f"days.day-{to_iso(day)}")
    assert isinstance(widget, tk.Button)
    return widget


def _panel(app: SickDaysApp) -> KeepPanel:
    (panel,) = app.host.winfo_children()
    assert isinstance(panel, KeepPanel)
    return panel


def test_an_empty_pool_says_none_ahead(tk_root: tk.Tk) -> None:
    app = SickDaysApp(tk_root)
    assert tk_root.title() == "Sick days"
    assert _text.NONE_AHEAD in _texts(tk_root)
    assert app.host.winfo_children() == []


def test_mark_a_day_from_the_calendar(tk_root: tk.Tk) -> None:
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
    assert app.status.cget("text") == _window.saved_message(
        SickDay(FUTURE, is_sick=True, keep=frozenset({"leetcode"})), FUTURE
    )
    assert "Kept: LeetCode" in _texts(tk_root)
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
        "sickdays.gui._text.free_day_predicate", lambda: lambda _d: True
    )
    app = SickDaysApp(tk_root)
    app.select(FUTURE)
    assert app.host.winfo_children() == []
    assert str(app.status.cget("text")).endswith("release it in Free days first.")
    assert str(app.status.cget("fg")).upper() == tok.DANGER


def test_a_sick_day_on_a_free_day_still_opens(
    tk_root: tk.Tk, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_sick_day(FUTURE)
    monkeypatch.setattr(
        "sickdays.gui._text.free_day_predicate", lambda: lambda _d: True
    )
    app = SickDaysApp(tk_root)
    app.select(FUTURE)
    assert _panel(app).nametowidget("actions.clear").winfo_exists()


def test_the_list_shows_upcoming_days_with_kept_lockers(tk_root: tk.Tk) -> None:
    add_sick_day(FUTURE, keep=["alarm", "workout"])
    add_sick_day(FUTURE + timedelta(days=1))
    texts = _texts(SickDaysApp(tk_root).calendar.master)
    assert _text.day_label(FUTURE) in texts
    assert "Kept: Workout lock, Wake alarm" in texts
    assert _text.NONE_AHEAD not in texts


def test_saved_message_wording() -> None:
    sick = SickDay(FUTURE, is_sick=True)
    label = _text.day_label(FUTURE)
    assert _window.saved_message(None, FUTURE) == f"{label}: nothing changed"
    assert _window.saved_message(sick, FUTURE).endswith("every locker stands down")
    cleared = SickDay(FUTURE, is_sick=False)
    assert _window.saved_message(cleared, FUTURE) == f"{label} is a normal day again"


def test_past_days_are_inert_and_faded(tk_root: tk.Tk) -> None:
    app = SickDaysApp(tk_root)
    first = today().replace(day=1)
    app.calendar.month = first - timedelta(days=1)
    app.calendar.redraw()
    cell = _cell(app, app.calendar.month.replace(day=1))
    assert str(cell.cget("state")) == "disabled"


def test_month_arrows_stop_at_the_phones_range(tk_root: tk.Tk) -> None:
    app = SickDaysApp(tk_root)
    first, last = _text.month_bounds(today())
    for _ in range(30):
        app.calendar.step(1)
    assert app.calendar.month == last
    for _ in range(30):
        app.calendar.step(-1)
    assert app.calendar.month == first
    back = app.calendar.nametowidget("header.prev")
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
