"""A real Tk root per test. Run under xvfb-run, never on kuhy's display."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Iterator

import pytest


@pytest.fixture
def root() -> Iterator[tk.Tk]:
    win = tk.Tk()
    win.geometry("480x320+0+0")
    yield win
    win.destroy()


class Opener:
    """Stands in for the browser launch: records URLs, opens nothing."""

    def __init__(self) -> None:
        self.urls: list[str] = []

    def __call__(self, url: str) -> None:
        self.urls.append(url)


@pytest.fixture
def opener() -> Opener:
    return Opener()
