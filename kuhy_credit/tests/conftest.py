"""A real Tk root per test, always on a private Xvfb display.

The session starts its own Xvfb and points DISPLAY at it, so a plain
``pytest`` run never opens windows on the desktop it was started from.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tkinter as tk
from collections.abc import Iterator

import pytest


@pytest.fixture(scope="session", autouse=True)
def private_display() -> Iterator[None]:
    xvfb = shutil.which("Xvfb")
    if xvfb is None:
        pytest.exit("Xvfb is required (the Tk tests never use the real display)", 2)
    read, write = os.pipe()
    proc = subprocess.Popen(
        [xvfb, "-displayfd", str(write), "-screen", "0", "1600x1200x24", "-nolisten", "tcp"],
        pass_fds=(write,),
        stderr=subprocess.DEVNULL,
    )
    os.close(write)
    with os.fdopen(read) as fd:
        number = fd.readline().strip()
    old = os.environ.get("DISPLAY")
    os.environ["DISPLAY"] = f":{number}"
    yield
    if old is None:
        os.environ.pop("DISPLAY", None)
    else:
        os.environ["DISPLAY"] = old
    proc.terminate()
    proc.wait(10)


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
