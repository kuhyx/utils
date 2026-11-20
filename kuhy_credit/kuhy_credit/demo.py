"""Tk demo: a gatelock-sized window with the credit in the bottom-right corner.

    python -m kuhy_credit.demo [--light]

Nothing opens until you click the logo and then the panel.
"""

from __future__ import annotations

import argparse
import tkinter as tk
from typing import TYPE_CHECKING

from kuhy_credit._data import DARK, LIGHT, SPACE_MD
from kuhy_credit.tk import KuhyCredit

if TYPE_CHECKING:
    from collections.abc import Callable


def build(
    root: tk.Tk, *, theme: str = "dark", opener: Callable[[str], object] | None = None
) -> KuhyCredit:
    """Fill ``root`` with a themed demo window and return its credit."""
    root.geometry("640x400")
    root.configure(bg=(DARK if theme == "dark" else LIGHT)["bg"])
    credit = KuhyCredit(root, theme=theme, opener=opener)
    credit.place(relx=1.0, rely=1.0, x=-SPACE_MD, y=-SPACE_MD, anchor="se")
    return credit


def main(argv: list[str] | None = None, *, root: tk.Tk | None = None) -> int:
    """Run the demo window; returns the exit code."""
    parser = argparse.ArgumentParser(description="kuhy credit Tk demo")
    parser.add_argument("--light", action="store_true", help="light theme")
    args = parser.parse_args(argv)
    win = root or tk.Tk()
    build(win, theme="light" if args.light else "dark")
    win.mainloop()
    return 0
