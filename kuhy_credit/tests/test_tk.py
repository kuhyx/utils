from __future__ import annotations

import tkinter as tk
import webbrowser

import pytest

from kuhy_credit import TEXT, URL
from kuhy_credit import tk as credit_tk
from kuhy_credit._data import DARK, LIGHT, LOGO_SHAPES


def _make(root: tk.Tk, opener, *, theme: str = "dark", corner: str = "se") -> credit_tk.KuhyCredit:
    credit = credit_tk.KuhyCredit(root, theme=theme, opener=opener)
    rel = {"se": (1.0, 1.0), "nw": (0.0, 0.0)}[corner]
    credit.place(relx=rel[0], rely=rel[1], anchor=corner)
    root.update()
    return credit


def _click(widget: tk.Misc) -> None:
    widget.event_generate("<Button-1>", x=2, y=2)
    widget.update()


def test_logo_draws_field_and_every_shape(root, opener) -> None:
    credit = _make(root, opener)
    assert len(credit.find_all()) == 1 + len(LOGO_SHAPES)
    assert not credit.is_open


def test_logo_click_opens_panel_with_logo_and_text(root, opener) -> None:
    credit = _make(root, opener)
    _click(credit)
    assert credit.is_open
    assert credit.panel.winfo_ismapped()
    assert credit.label.cget("text") == TEXT
    assert len(credit.panel_logo.find_all()) == 1 + len(LOGO_SHAPES)
    assert opener.urls == []


@pytest.mark.parametrize("target", ["panel", "label", "panel_logo"])
def test_panel_click_opens_the_url_and_closes(root, opener, target: str) -> None:
    credit = _make(root, opener)
    _click(credit)
    _click(getattr(credit, target))
    assert opener.urls == [URL]
    assert not credit.is_open


def test_escape_closes_without_opening(root, opener) -> None:
    credit = _make(root, opener)
    _click(credit)
    credit.panel.focus_force()
    root.update()
    credit.panel.event_generate("<Escape>")
    root.update()
    assert not credit.is_open
    assert opener.urls == []


def test_outside_click_closes(root, opener) -> None:
    other = tk.Frame(root, width=50, height=50)
    other.place(x=200, y=100)
    credit = _make(root, opener)
    _click(credit)
    _click(other)
    assert not credit.is_open
    assert opener.urls == []


def test_second_logo_click_closes_and_stays_closed(root, opener) -> None:
    credit = _make(root, opener)
    _click(credit)
    _click(credit)
    root.update()
    assert not credit.is_open
    assert opener.urls == []


@pytest.mark.parametrize("key", ["<Return>", "<space>"])
def test_keyboard_opens_panel_then_url(root, opener, key: str) -> None:
    credit = _make(root, opener)
    assert int(credit.cget("takefocus")) == 1
    assert root.tk_focusNext() is credit  # Tab reaches the logo
    credit.focus_force()
    root.update()
    credit.event_generate(key)
    root.update()
    assert credit.is_open
    assert root.focus_get() is credit.panel
    credit.panel.event_generate(key)
    root.update()
    assert opener.urls == [URL]


def test_click_outside_when_closed_is_ignored(root, opener) -> None:
    credit = _make(root, opener)
    _click(root)
    assert not credit.is_open


@pytest.mark.parametrize(("theme", "pal"), [("dark", DARK), ("light", LIGHT)])
def test_theme_colours_come_from_tokens(root, opener, theme: str, pal: dict) -> None:
    credit = _make(root, opener, theme=theme)
    assert credit.panel.cget("bg") == pal["surface"]
    assert credit.panel.cget("highlightbackground") == pal["border"]
    assert credit.label.cget("fg") == pal["text"]


def test_unknown_theme_is_rejected(root, opener) -> None:
    with pytest.raises(ValueError, match="theme"):
        credit_tk.KuhyCredit(root, theme="blue", opener=opener)


def test_panel_sits_above_a_bottom_right_logo(root, opener) -> None:
    credit = _make(root, opener, corner="se")
    _click(credit)
    assert credit.panel.winfo_y() < credit.winfo_y()
    assert credit.panel.winfo_x() + credit.panel.winfo_width() <= root.winfo_width()


def test_panel_sits_below_a_top_left_logo(root, opener) -> None:
    credit = _make(root, opener, corner="nw")
    _click(credit)
    assert credit.panel.winfo_y() > credit.winfo_y()
    assert credit.panel.winfo_x() == credit.winfo_x()


def test_default_opener_uses_a_new_browser_tab(monkeypatch: pytest.MonkeyPatch, root) -> None:
    seen = []
    monkeypatch.setattr(webbrowser, "open", lambda url, new=0: seen.append((url, new)))
    credit = _make(root, None)
    _click(credit)
    _click(credit.panel)
    assert seen == [(URL, 2)]


def test_escape_when_closed_keeps_focus_where_it_is(root, opener) -> None:
    entry = tk.Entry(root)
    entry.place(x=10, y=10)
    _make(root, opener)
    entry.focus_force()
    root.update()
    entry.event_generate("<Escape>")
    root.update()
    assert root.focus_get() is entry
