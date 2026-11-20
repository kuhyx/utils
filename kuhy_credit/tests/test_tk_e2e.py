"""E2E: the demo window, two pointer clicks hit-tested at screen coordinates."""

from __future__ import annotations

import tkinter as tk

import pytest

from kuhy_credit import URL, demo


def _click_at_centre_of(root: tk.Tk, widget: tk.Misc) -> None:
    """Click whatever widget sits under the centre of ``widget`` on screen."""
    root.update()
    x = widget.winfo_rootx() + widget.winfo_width() // 2
    y = widget.winfo_rooty() + widget.winfo_height() // 2
    hit = root.winfo_containing(x, y)
    assert hit is not None
    hit.event_generate("<Button-1>", x=x - hit.winfo_rootx(), y=y - hit.winfo_rooty())
    root.update()


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_two_clicks_open_the_website(root, opener, theme: str) -> None:
    credit = demo.build(root, theme=theme, opener=opener)
    _click_at_centre_of(root, credit)
    assert credit.is_open
    assert opener.urls == []
    _click_at_centre_of(root, credit.label)
    assert opener.urls == [URL]
    assert not credit.is_open


def test_main_runs_the_window(root, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(root, "mainloop", lambda: None)
    assert demo.main(["--light"], root=root) == 0
    assert demo.main([], root=root) == 0


def test_main_creates_its_own_root(monkeypatch: pytest.MonkeyPatch) -> None:
    made = []

    class FakeTk(tk.Tk):
        def mainloop(self, n: int = 0) -> None:
            made.append(self)
            self.destroy()

    monkeypatch.setattr(tk, "Tk", FakeTk)
    assert demo.main([]) == 0
    assert len(made) == 1
