# Copyright (c) 2026 Krzysztof Rudnicki
"""The word-free controls and the drawn icons, against a real Tk."""

from __future__ import annotations

import tkinter as tk

import pytest

from sickdays._constants import LOCKERS
from sickdays.gui import _tokens as tok
from sickdays.gui._controls import IconButton, IconSlot, Toggle
from sickdays.gui._icons import ICONS, LOCKER_ICONS, TAG


@pytest.fixture
def shown(tk_root: tk.Tk) -> tk.Tk:
    """The root mapped, so real clicks reach the canvases."""
    tk_root.deiconify()
    tk_root.update()
    return tk_root


def _click(widget: tk.Canvas) -> None:
    widget.pack()
    widget.update()
    widget.event_generate("<Button-1>", x=2, y=2)
    widget.update()


def test_every_icon_draws_something(tk_root: tk.Tk) -> None:
    for icon in ICONS:
        slot = IconSlot(tk_root, size=32).show(icon, tok.DANGER)
        assert slot.icon == icon
        assert slot.find_withtag(TAG), icon
    assert slot.show(None).icon is None
    assert slot.find_withtag(TAG) == ()


def test_every_locker_has_an_icon() -> None:
    assert set(LOCKER_ICONS) == set(LOCKERS)
    assert set(LOCKER_ICONS.values()) <= set(ICONS)


def test_a_click_invokes_the_button_unless_disabled(shown: tk.Tk) -> None:
    calls: list[int] = []
    button = IconButton(shown, "check", lambda: calls.append(1), name="ok")
    button.set_enabled(False)
    assert str(button.cget("cursor")) == "arrow"
    _click(button)
    button.invoke()
    assert calls == []
    button.set_enabled(True)
    _click(button)
    assert calls == [1]


def test_a_click_flips_the_switch_unless_disabled(shown: tk.Tk) -> None:
    on = tk.BooleanVar(shown, value=False)
    switch = Toggle(shown, on, name="switch")
    _click(switch)
    assert switch.is_on()
    assert on.get()
    switch.set_enabled(False)
    _click(switch)
    switch.invoke()
    assert switch.is_on()
    switch.set_enabled(True)
    switch.invoke()
    assert not switch.is_on()
