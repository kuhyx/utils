# Copyright (c) 2026 Krzysztof Rudnicki
"""KeepPanel: the five switches for one day, against a real (unmapped) Tk."""

from __future__ import annotations

from datetime import timedelta
import tkinter as tk
from typing import TYPE_CHECKING

import pytest

from sickdays._api import add_sick_day, is_sick_day
from sickdays._day import today
from sickdays._errors import ConflictCheckUnavailableError
from sickdays._keep_api import kept_lockers
from sickdays._paths import Paths
from sickdays.gui import KeepPanel, _text
from sickdays.gui import _tokens as tok

if TYPE_CHECKING:
    from pathlib import Path

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


def _button(panel: KeepPanel, name: str) -> tk.Button:
    widget = panel.nametowidget(f"actions.{name}")
    assert isinstance(widget, tk.Button)
    return widget


def _toggle(panel: KeepPanel, locker: str) -> tk.Checkbutton:
    widget = panel.nametowidget(f"keep-{locker}")
    assert isinstance(widget, tk.Checkbutton)
    return widget


def _status(panel: KeepPanel) -> str:
    return str(panel.nametowidget("status").cget("text"))


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
    assert toggle.cget("text") == "Off"
    toggle.invoke()
    assert toggle.cget("text") == "On"
    assert str(toggle.cget("bg")).upper() == tok.ACCENT
    assert str(toggle.cget("fg")).upper() == tok.ON_FILL
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
    title = panel.nametowidget("title").cget("text")
    assert title == f"Sick day: {_text.day_label(FUTURE)}"


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
    assert _status(panel) == _text.PAST_NOTE
    assert _actions(panel) == set()
    assert str(_toggle(panel, "diet").cget("state")) == "disabled"


def test_a_free_day_is_refused_with_the_phones_message(
    tk_root: tk.Tk, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "sickdays.gui._text.free_day_predicate", lambda: lambda _d: True
    )
    panel = KeepPanel(tk_root, FUTURE, on_saved=lambda _e: None)
    expected = "is a free day — release it in Free days first."
    assert _status(panel).endswith(expected)
    assert _actions(panel) == set()


def test_an_uncheckable_free_pool_refuses(
    tk_root: tk.Tk, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable() -> None:
        msg = "cannot check the free-day pool"
        raise ConflictCheckUnavailableError(msg)

    monkeypatch.setattr("sickdays.gui._text.free_day_predicate", unavailable)
    panel = KeepPanel(tk_root, FUTURE, on_saved=lambda _e: None)
    assert _status(panel) == "cannot check the free-day pool"
    assert _actions(panel) == set()


def test_a_refused_write_is_shown_not_raised(
    tk_root: tk.Tk, synced: list[Paths | None]
) -> None:
    saved: list[SickDay | None] = []
    panel = KeepPanel(tk_root, FUTURE, on_saved=saved.append)
    add_sick_day(FUTURE)  # marked elsewhere while the panel was open
    _button(panel, "mark").invoke()
    assert "already a sick day" in _status(panel)
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
    _button(panel, "cancel").invoke()
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
