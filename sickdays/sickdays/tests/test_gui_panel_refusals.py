# Copyright (c) 2026 Krzysztof Rudnicki
"""KeepPanel refusals: past days, free days, failed writes, cancel and paths."""

from __future__ import annotations

from datetime import timedelta
import logging
import threading
from typing import TYPE_CHECKING

from sickdays._api import add_sick_day, is_sick_day, load
from sickdays._day import today
from sickdays._errors import ConflictCheckUnavailableError
from sickdays._paths import Paths
from sickdays._store import write_pool
from sickdays.gui import KeepPanel
from sickdays.gui._controls import IconSlot
from sickdays.tests._panel_probe import (
    FUTURE,
    action_names,
    find_button,
    find_toggle,
    join_sync,
    status_icon,
)

if TYPE_CHECKING:
    from pathlib import Path
    import tkinter as tk

    import pytest

    from sickdays._model import SickDay


def test_a_past_day_is_shown_but_not_editable(tk_root: tk.Tk) -> None:
    panel = KeepPanel(tk_root, today() - timedelta(days=1), on_saved=lambda _e: None)
    assert panel.reason == "past"
    assert status_icon(panel) == "padlock"
    assert action_names(panel) == set()
    diet = find_toggle(panel, "diet")
    assert str(diet.cget("state")) == "disabled"
    diet.invoke()
    assert not diet.is_on()


def test_a_free_day_is_refused_with_the_phones_message(
    tk_root: tk.Tk, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "sickdays.gui._dates.free_day_predicate", lambda: lambda _d: True
    )
    panel = KeepPanel(tk_root, FUTURE, on_saved=lambda _e: None)
    assert panel.reason == "free"
    assert status_icon(panel) == "no_entry"
    state = panel.nametowidget("head.state")
    assert isinstance(state, IconSlot)
    assert state.icon == "normal"
    assert action_names(panel) == set()


def test_an_uncheckable_free_pool_refuses(
    tk_root: tk.Tk, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable() -> None:
        msg = "cannot check the free-day pool"
        raise ConflictCheckUnavailableError(msg)

    monkeypatch.setattr("sickdays.gui._dates.free_day_predicate", unavailable)
    panel = KeepPanel(tk_root, FUTURE, on_saved=lambda _e: None)
    assert panel.reason == "unavailable"
    assert status_icon(panel) == "warning"
    assert action_names(panel) == set()


def test_a_refused_write_is_shown_not_raised(
    tk_root: tk.Tk, synced: list[Paths | None], caplog: pytest.LogCaptureFixture
) -> None:
    saved: list[SickDay | None] = []
    panel = KeepPanel(tk_root, FUTURE, on_saved=saved.append)
    add_sick_day(FUTURE)  # marked elsewhere while the panel was open
    with caplog.at_level(logging.WARNING):
        find_button(panel, "mark").invoke()
    assert panel.reason == "refused"
    assert status_icon(panel) == "warning"
    assert "already a sick day" in caplog.text
    assert saved == []
    assert synced == []


def test_cancel_calls_back(tk_root: tk.Tk) -> None:
    cancelled: list[bool] = []
    panel = KeepPanel(
        tk_root,
        FUTURE,
        on_saved=lambda _e: None,
        on_cancel=lambda: cancelled.append(True),
    )
    cancel = find_button(panel, "cancel")
    assert cancel.icon == "cross"
    cancel.invoke()
    assert cancelled == [True]


def test_explicit_paths_are_used_for_every_read_write_and_sync(
    tk_root: tk.Tk, synced: list[Paths | None], tmp_path: Path
) -> None:
    other = Paths.under(tmp_path / "other")
    add_sick_day(FUTURE, keep=["book"], paths=other)
    panel = KeepPanel(tk_root, FUTURE, on_saved=lambda _e: None, paths=other)
    assert panel.kept() == frozenset({"book"})
    find_button(panel, "clear").invoke()
    join_sync(panel)
    assert not is_sick_day(FUTURE, log_path=other.log)
    assert synced == [other]
    assert not (tmp_path / "state" / "sick_days.json").exists()


def test_a_write_during_a_sync_is_refused_not_lost(
    tk_root: tk.Tk, monkeypatch: pytest.MonkeyPatch
) -> None:
    """sync() reads the pool, waits on the network, then writes its merged
    copy back: a write landing in that window would be silently overwritten.
    """
    loaded = threading.Event()
    release = threading.Event()
    calls: list[int] = []

    def slow_sync(*, paths: Paths | None = None) -> bool:
        calls.append(1)
        if len(calls) > 1 or paths is None:
            return False
        snapshot = load(paths.log)
        loaded.set()
        release.wait(timeout=5)
        write_pool(paths.log, snapshot)
        return True

    monkeypatch.setattr("sickdays.gui._panel.sync_quietly", slow_sync)
    saved: list[SickDay | None] = []
    first = KeepPanel(tk_root, FUTURE, on_saved=saved.append)
    find_button(first, "mark").invoke()
    assert loaded.wait(timeout=5)
    later = FUTURE + timedelta(days=1)
    second = KeepPanel(tk_root, later, on_saved=saved.append)
    find_button(second, "mark").invoke()
    release.set()
    join_sync(first)
    if second.sync_thread is not None:
        second.sync_thread.join(timeout=5)
    for entry in saved:
        assert entry is not None
        assert is_sick_day(entry.day), f"{entry.day} was written, then lost"
    assert second.reason == "busy"
    assert status_icon(second) == "hourglass"
