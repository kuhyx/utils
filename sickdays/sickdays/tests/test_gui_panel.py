# Copyright (c) 2026 Krzysztof Rudnicki
"""KeepPanel: the six switches for one day, against a real (unmapped) Tk."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sickdays._api import add_sick_day, is_sick_day
from sickdays._day import to_iso
from sickdays._keep_api import kept_lockers
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

    from sickdays._model import SickDay
    from sickdays._paths import Paths


def test_mark_sick_keeping_leetcode(tk_root: tk.Tk, synced: list[Paths | None]) -> None:
    saved: list[SickDay | None] = []
    panel = KeepPanel(tk_root, FUTURE, on_saved=saved.append)
    assert panel.kept() == frozenset()
    assert action_names(panel) == {"mark"}
    toggle = find_toggle(panel, "leetcode")
    assert not toggle.is_on()
    toggle.invoke()
    assert toggle.is_on()
    assert find_button(panel, "mark").icon == "check"
    assert status_icon(panel) is None
    find_button(panel, "mark").invoke()
    join_sync(panel)
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
    assert action_names(panel) == {"save", "clear"}
    assert panel.nametowidget("head.title").cget("text") == to_iso(FUTURE)
    state = panel.nametowidget("head.state")
    assert isinstance(state, IconSlot)
    assert state.icon == "sick"
    assert find_button(panel, "clear").icon == "trash"
    icon = panel.nametowidget("icon-workout")
    assert isinstance(icon, IconSlot)
    assert icon.icon == "workout"


def test_save_replaces_the_kept_set(tk_root: tk.Tk, synced: list[Paths | None]) -> None:
    add_sick_day(FUTURE, keep=["workout"])
    saved: list[SickDay | None] = []
    panel = KeepPanel(tk_root, FUTURE, on_saved=saved.append)
    find_toggle(panel, "workout").invoke()
    find_toggle(panel, "diet").invoke()
    find_button(panel, "save").invoke()
    join_sync(panel)
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
    find_button(panel, "save").invoke()
    assert saved == [None]
    assert panel.sync_thread is None
    assert synced == []
    assert (state_dir / "audit.jsonl").read_text(encoding="utf-8") == before


def test_clear_makes_the_day_normal(tk_root: tk.Tk, synced: list[Paths | None]) -> None:
    add_sick_day(FUTURE, keep=["alarm"])
    saved: list[SickDay | None] = []
    panel = KeepPanel(tk_root, FUTURE, on_saved=saved.append)
    find_button(panel, "clear").invoke()
    join_sync(panel)
    assert not is_sick_day(FUTURE)
    assert saved[0] is not None
    assert not saved[0].is_sick
    assert len(synced) == 1
