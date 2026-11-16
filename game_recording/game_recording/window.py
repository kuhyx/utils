# Copyright (c) 2026 Krzysztof Rudnicki
"""Finds the game's X11 window by process id (xdotool)."""

from dataclasses import dataclass
import subprocess
import time
from typing import TYPE_CHECKING

from game_recording import procs

if TYPE_CHECKING:
    from collections.abc import Callable

MIN_SIDE = 64  # smaller is a helper window, not the game
STABLE_POLLS = 3  # the same id and size this many polls in a row


@dataclass(frozen=True)
class Window:
    """A visible X11 window."""

    id: int
    width: int
    height: int


def _run(*args: str) -> str:
    done = subprocess.run([procs.program("xdotool"), *args], capture_output=True, text=True, check=False, timeout=10)
    return "" if done.returncode else done.stdout


def _geometry(win_id: str) -> Window | None:
    fields = dict(
        line.split("=", 1) for line in _run("getwindowgeometry", "--shell", win_id).splitlines() if "=" in line
    )
    try:
        return Window(int(win_id), int(fields["WIDTH"]), int(fields["HEIGHT"]))
    except KeyError, ValueError:
        return None


def largest(pid: int) -> Window | None:
    """The biggest visible window of the process, None when it has none yet."""
    found = (_geometry(i) for i in _run("search", "--onlyvisible", "--pid", str(pid)).split())
    sized = [w for w in found if w is not None and w.width >= MIN_SIDE and w.height >= MIN_SIDE]
    if not sized:
        return None
    return max(sized, key=lambda w: w.width * w.height)


def wait_stable(pid: int, timeout_s: float, alive: Callable[[], bool], poll_s: float = 0.25) -> Window | None:
    """The game's window once its id and size stop changing (it resizes while starting)."""
    deadline = time.monotonic() + timeout_s
    last: Window | None = None
    seen = 0
    while time.monotonic() < deadline and alive():
        current = largest(pid)
        seen = seen + 1 if current is not None and current == last else 1
        last = current
        if current is not None and seen >= STABLE_POLLS:
            return current
        time.sleep(poll_s)
    return None
