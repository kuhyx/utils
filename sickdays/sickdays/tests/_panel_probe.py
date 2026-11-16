# Copyright (c) 2026 Krzysztof Rudnicki
"""Shared probes for the KeepPanel tests: find its widgets by name."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from sickdays._day import today
from sickdays.gui._controls import IconButton, IconSlot, Toggle

if TYPE_CHECKING:
    from sickdays.gui import KeepPanel

#: A day far enough ahead to stay editable for the whole run.
FUTURE = today() + timedelta(days=3)


def find_button(panel: KeepPanel, name: str) -> IconButton:
    """The action button called ``name``."""
    widget = panel.nametowidget(f"actions.{name}")
    assert isinstance(widget, IconButton)
    return widget


def find_toggle(panel: KeepPanel, locker: str) -> Toggle:
    """The keep switch for ``locker``."""
    widget = panel.nametowidget(f"keep-{locker}")
    assert isinstance(widget, Toggle)
    return widget


def status_icon(panel: KeepPanel) -> str | None:
    """The status slot's icon, or None when it is blank."""
    slot = panel.nametowidget("status")
    assert isinstance(slot, IconSlot)
    return slot.icon


def action_names(panel: KeepPanel) -> set[str]:
    """The names of the action buttons shown now."""
    actions = panel.nametowidget("actions")
    return {child.winfo_name() for child in actions.winfo_children()}


def join_sync(panel: KeepPanel) -> None:
    """Wait for the panel's background sync to finish."""
    assert panel.sync_thread is not None
    panel.sync_thread.join(timeout=5)
