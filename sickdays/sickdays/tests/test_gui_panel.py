# Copyright (c) 2026 Krzysztof Rudnicki
"""KeepPanel: the six switches for one day, against a real (unmapped) Tk."""

from __future__ import annotations

from datetime import timedelta
import logging
import threading
from typing import TYPE_CHECKING

import pytest

from sickdays._api import add_sick_day, is_sick_day, load
from sickdays._day import to_iso, today
from sickdays._errors import ConflictCheckUnavailableError
from sickdays._keep_api import kept_lockers
from sickdays._paths import Paths
from sickdays._store import write_pool
from sickdays.gui import KeepPanel
from sickdays.gui._controls import IconButton, IconSlot, Toggle

if TYPE_CHECKING:
    from pathlib import Path
    import tkinter as tk

    from sickdays._model import SickDay

FUTURE = today() + timedelta(days=3)


@pytest.fixture
def synced(monkeypatch: pytest.MonkeyPatch) -> list[Paths | None]:
    """Record every background sync the panel starts."""
    calls: list[Paths | None] = []

    def record(*, paths: Paths | None = None) -> bool:
        calls.append(paths)
        return True

    monkeypatch.setattr("sickdays.gui._panel.sync_quietly", record)
    return calls


def _button(panel: KeepPanel, name: str) -> IconButton:
    widget = panel.nametowidget(f"actions.{name}")
    assert isinstance(widget, IconButton)
    return widget


def _toggle(panel: KeepPanel, locker: str) -> Toggle:
    widget = panel.nametowidget(f"keep-{locker}")
    assert isinstance(widget, Toggle)
    return widget


def _status(panel: KeepPanel) -> str | None:
    slot = panel.nametowidget("status")
    assert isinstance(slot, IconSlot)
    return slot.icon


def _actions(panel: KeepPanel) -> set[str]:
    actions = panel.nametowidget("actions")
    return {child.winfo_name() for child in actions.winfo_children()}


def _join(panel: KeepPanel) -> None:
    assert panel.sync_thread is not None
    panel.sync_thread.join(timeout=5)


def test_mark_sick_keeping_leetcode(tk_root: tk.Tk, synced: list[Paths | None]) -> None:
    saved: list[SickDay | None] = []
    panel = KeepPanel(tk_root, FUTURE, on_saved=saved.append)
    assert panel.kept() == frozenset()
    assert _actions(panel) == {"mark"}
    toggle = _toggle(panel, "leetcode")
    assert not toggle.is_on()
    toggle.invoke()
    assert toggle.is_on()
    assert _button(panel, "mark").icon == "check"
    assert _status(panel) is None
    _button(panel, "mark").invoke()
    _join(panel)
    assert is_sick_day(FUTURE)
    assert kept_lockers(FUTURE) == frozenset({"leetcode"})
    assert len(saved) == 1
    assert saved[0] is not None
    assert saved[0].is_sick
    assert saved[0].keep == frozenset({"leetcode"})
    assert len(synced) == 1


def test_an_existing_sick_day_opens_with_its_switches(tk_root: tk.Tk) -> None:
    add_sick_day(FUTURE, keep=["workout"])
    panel = KeepPanel(tk_root, FUTURE, on_saved=lambda _entry: None)
    assert panel.kept() == frozenset({"workout"})
    assert _actions(panel) == {"save", "clear"}
    assert panel.nametowidget("head.title").cget("text") == to_iso(FUTURE)
    state = panel.nametowidget("head.state")
    assert isinstance(state, IconSlot)
    assert state.icon == "sick"
    assert _button(panel, "clear").icon == "trash"
    icon = panel.nametowidget("icon-workout")
    assert isinstance(icon, IconSlot)
    assert icon.icon == "workout"


def test_save_replaces_the_kept_set(tk_root: tk.Tk, synced: list[Paths | None]) -> None:
    add_sick_day(FUTURE, keep=["workout"])
    saved: list[SickDay | None] = []
    panel = KeepPanel(tk_root, FUTURE, on_saved=saved.append)
    _toggle(panel, "workout").invoke()
    _toggle(panel, "diet").invoke()
    _button(panel, "save").invoke()
    _join(panel)
    assert kept_lockers(FUTURE) == frozenset({"diet"})
    assert saved[0] is not None
    assert saved[0].keep == frozenset({"diet"})
    assert len(synced) == 1


def test_an_unchanged_save_writes_nothing(
    tk_root: tk.Tk, synced: list[Paths | None], state_dir: Path
) -> None:
    add_sick_day(FUTURE, keep=["book"])
    before = (state_dir / "audit.jsonl").read_text(encoding="utf-8")
    saved: list[SickDay | None] = []
    panel = KeepPanel(tk_root, FUTURE, on_saved=saved.append)
    _button(panel, "save").invoke()
    assert saved == [None]
    assert panel.sync_thread is None
    assert synced == []
    assert (state_dir / "audit.jsonl").read_text(encoding="utf-8") == before


def test_clear_makes_the_day_normal(tk_root: tk.Tk, synced: list[Paths | None]) -> None:
    add_sick_day(FUTURE, keep=["alarm"])
    saved: list[SickDay | None] = []
    panel = KeepPanel(tk_root, FUTURE, on_saved=saved.append)
    _button(panel, "clear").invoke()
    _join(panel)
    assert not is_sick_day(FUTURE)
    assert saved[0] is not None
    assert not saved[0].is_sick
    assert len(synced) == 1


def test_a_past_day_is_shown_but_not_editable(tk_root: tk.Tk) -> None:
    panel = KeepPanel(tk_root, today() - timedelta(days=1), on_saved=lambda _e: None)
    assert panel.reason == "past"
    assert _status(panel) == "padlock"
    assert _actions(panel) == set()
    diet = _toggle(panel, "diet")
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
    assert _status(panel) == "no_entry"
    state = panel.nametowidget("head.state")
    assert isinstance(state, IconSlot)
    assert state.icon == "normal"
    assert _actions(panel) == set()


def test_an_uncheckable_free_pool_refuses(
    tk_root: tk.Tk, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable() -> None:
        msg = "cannot check the free-day pool"
        raise ConflictCheckUnavailableError(msg)

    monkeypatch.setattr("sickdays.gui._dates.free_day_predicate", unavailable)
    panel = KeepPanel(tk_root, FUTURE, on_saved=lambda _e: None)
    assert panel.reason == "unavailable"
    assert _status(panel) == "warning"
    assert _actions(panel) == set()


def test_a_refused_write_is_shown_not_raised(
    tk_root: tk.Tk, synced: list[Paths | None], caplog: pytest.LogCaptureFixture
) -> None:
    saved: list[SickDay | None] = []
    panel = KeepPanel(tk_root, FUTURE, on_saved=saved.append)
    add_sick_day(FUTURE)  # marked elsewhere while the panel was open
    with caplog.at_level(logging.WARNING):
        _button(panel, "mark").invoke()
    assert panel.reason == "refused"
    assert _status(panel) == "warning"
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
    cancel = _button(panel, "cancel")
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
    _button(panel, "clear").invoke()
    _join(panel)
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
    _button(first, "mark").invoke()
    assert loaded.wait(timeout=5)
    later = FUTURE + timedelta(days=1)
    second = KeepPanel(tk_root, later, on_saved=saved.append)
    _button(second, "mark").invoke()
    release.set()
    _join(first)
    if second.sync_thread is not None:
        second.sync_thread.join(timeout=5)
    for entry in saved:
        assert entry is not None
        assert is_sick_day(entry.day), f"{entry.day} was written, then lost"
    assert second.reason == "busy"
    assert _status(second) == "hourglass"
