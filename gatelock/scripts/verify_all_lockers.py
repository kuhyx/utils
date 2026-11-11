#!/usr/bin/env python3
# Copyright (c) 2026 Krzysztof Rudnicki
# pylint: disable=missing-function-docstring,consider-using-with,import-error
r"""All lockers at once, on a real X server: one lock at a time, each clickable.

Starts the five lockers that fire together at login (real app names and ranks,
the real ``Arbiter`` + ``wait_for_turn`` startup, one process each, a private
``GATELOCK_RUNTIME_DIR``) with a ``gcr-prompter`` grab helper started first, as
on 2026-11-11. Asserts: never two locks on screen; once the prompt lets go the
lone lock holds the grab; an XTEST click on its button fires its callback; when
it closes the next one comes up the same way. The queue poll is 0.5 s (real:
2 s) to fit the 60 s cap. Argument: launch order -- mixed, strong-first,
weak-first, or late-strong (screen_locker starts 3 s after the rest, once a
weaker lock holds the grab). Xvfb only (XTEST); refuses ``:0``::

    PYTHONPATH=. xvfb-run -a -s "-screen 0 1600x1200x24" \
        python3 scripts/verify_all_lockers.py
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import select
import subprocess
import sys
import tempfile
import time
from typing import TYPE_CHECKING, Final

from Xlib import X, display, error
from Xlib.ext import xtest

if TYPE_CHECKING:
    from collections.abc import Callable

HERE: Final = Path(__file__).parent
LOCKERS: Final = {  # app -> rank, as in each locker's own constants
    "screen_locker": 200,
    "leetcode_guard": 150,
    "book_guard": 125,
    "focus_guard": 120,
    "diet_guard": 100,
}
_RANKED: Final = tuple(sorted(LOCKERS, key=lambda a: -LOCKERS[a]))
ORDERS: Final = {  # launch order: how the five processes race to publish
    "mixed": tuple(_RANKED[i] for i in (4, 1, 3, 0, 2)),
    "strong-first": _RANKED,
    "weak-first": _RANKED[::-1],
    "late-strong": tuple(sorted(set(LOCKERS) - {"screen_locker"})),
}
LATE: Final = {"late-strong": ("screen_locker", 3.0, 2.0)}  # app, start s, hold s
POLL_S, STEP_S, PROMPT_HOLD_S, SHOW_S, GRAB_S, CLICK_S = 0.5, 0.1, 6.0, 12.0, 8.0, 5.0
SETTLE_S = 1.0


def _say(message: str) -> None:
    sys.stdout.write(f"{message}\n")


class _Fleet:
    """The child processes and what they have reported so far."""

    def __init__(self, env: dict[str, str], launch: tuple[str, ...]) -> None:
        self.env = env
        self.procs: dict[str, subprocess.Popen[bytes]] = {}
        self.buffers = dict.fromkeys(LOCKERS, b"")
        self.grab = dict.fromkeys(LOCKERS, 0)
        self.button: dict[str, tuple[int, int]] = {}
        self.clicked: set[str] = set()
        self.armed: set[str] = set()
        for app in launch:
            self.launch(app)

    def launch(self, app: str) -> None:
        args = [sys.executable, str(HERE / "locker_child.py"), app]
        args += [str(LOCKERS[app]), str(POLL_S)]
        self.procs[app] = subprocess.Popen(args, stdout=subprocess.PIPE, env=self.env)

    def drain(self) -> None:
        fds = {p.stdout.fileno(): a for a, p in self.procs.items() if p.stdout}
        for fd in select.select(list(fds), [], [], 0)[0]:
            app = fds[fd]
            self.buffers[app] += os.read(fd, 65536)
            *lines, self.buffers[app] = self.buffers[app].split(b"\n")
            for raw in lines:
                self.note(app, raw.decode())

    def note(self, app: str, line: str) -> None:
        if line == "ARMED":
            self.armed.add(app)
        elif line == "CLICKED":
            self.clicked.add(app)
        elif m := re.fullmatch(r"GRAB (\d)", line):
            self.grab[app] = int(m[1])
        elif m := re.fullmatch(r"BTN (\d+) (\d+)", line):
            self.button[app] = (int(m[1]), int(m[2]))
        elif line.startswith("ERROR"):
            _say(f"FAIL {app} reported {line}")

    def stop(self) -> None:
        for proc in self.procs.values():
            proc.terminate()
        for proc in self.procs.values():
            proc.wait(timeout=10)


class _Screen:
    """Which locks are on screen, and a synthetic mouse."""

    def __init__(self) -> None:
        self.display = display.Display()
        self.root = self.display.screen().root

    def shown(self) -> set[str]:
        apps: set[str] = set()
        try:
            for child in self.root.query_tree().children:
                if child.get_attributes().map_state != X.IsViewable:
                    continue
                for win in (child, *child.query_tree().children):
                    found = win.get_wm_class()
                    if found and found[1].lower() in LOCKERS:
                        apps.add(found[1].lower())
        except error.XError as exc:  # a lock closed mid-walk: next sample
            _say(f"note: window vanished mid-sample ({exc})")
        return apps

    def click(self, x: int, y: int) -> None:
        # Approach from off-target: Tk learns which widget is under the pointer
        # from Enter/Motion events, and the previous lock's button sat at this
        # very spot, so a motion to the same coordinates would produce none.
        for px, py in ((x - 30, y - 30), (x, y)):
            xtest.fake_input(self.display, X.MotionNotify, x=px, y=py)
            self.display.sync()
            time.sleep(0.15)
        xtest.fake_input(self.display, X.ButtonPress, 1)
        xtest.fake_input(self.display, X.ButtonRelease, 1)
        self.display.sync()


class _Run:
    """Pumps the fleet and samples the screen; remembers any double lock."""

    def __init__(self, fleet: _Fleet, screen: _Screen) -> None:
        self.fleet = fleet
        self.screen = screen
        self.doubles: list[list[str]] = []

    def pump(self, seconds: float, until: Callable[[], bool] | None = None) -> bool:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.fleet.drain()
            shown = self.screen.shown()
            if len(shown) > 1:
                self.doubles.append(sorted(shown))
            if until is not None and until():
                return True
            time.sleep(STEP_S)
        return until() if until is not None else False

    def lone(self, seen: list[str]) -> str | None:
        """Wait for exactly one new lock on screen; return its app."""
        got = self.pump(
            SHOW_S,
            lambda: len(shown := self.screen.shown()) == 1 and not shown & set(seen),
        )
        return next(iter(self.screen.shown())) if got else None


def _drive(run: _Run, check: Callable[[object, str], None]) -> list[str]:
    """Click each lock that appears, in turn; returns the order seen."""
    order: list[str] = []
    fleet = run.fleet
    for _ in LOCKERS:
        app = run.lone(order)
        check(app, f"lock #{len(order) + 1} came up alone ({app})")
        if not app:
            break
        order.append(app)
        ready = run.pump(GRAB_S, lambda a=app: fleet.grab[a] == 1 and a in fleet.button)
        check(ready, f"{app}: holds the grab and shows its button")
        if ready:
            run.pump(SETTLE_S)
            run.screen.click(*fleet.button[app])
        check(
            run.pump(CLICK_S, lambda a=app: a in fleet.clicked),
            f"{app}: XTEST click fired the callback",
        )
    return order


def main(mode: str) -> int:
    """Run the scenario on a private display; 0 when every check held."""
    if os.environ.get("DISPLAY", "").split(".")[0] in {"", ":0"}:
        _say("refusing to run: DISPLAY must be a private X server, never :0")
        return 2
    if mode not in ORDERS:
        _say(f"usage: verify_all_lockers.py [{'|'.join(ORDERS)}]")
        return 2
    env = {**os.environ, "GATELOCK_RUNTIME_DIR": tempfile.mkdtemp(prefix="gl-lockers-")}
    failures: list[str] = []

    def check(ok: object, label: str) -> None:
        _say(f"{'PASS' if ok else 'FAIL'} {label}")
        if not ok:
            failures.append(label)

    helper = subprocess.Popen(
        [sys.executable, str(HERE / "prompt_grab_helper.py"), "gcr-prompter"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    check(
        helper.stdout is not None and helper.stdout.readline().strip() == "READY",
        "prompt holds the grab",
    )
    fleet = _Fleet(env, ORDERS[mode])
    run = _Run(fleet, _Screen())
    try:
        run.pump(LATE[mode][2] if mode in LATE else PROMPT_HOLD_S)
        check(not run.doubles, "while the prompt held the grab: never two locks")
        if helper.stdin:
            helper.stdin.write("release\n")
            helper.stdin.flush()
        if mode in LATE:
            late, at, hold = LATE[mode]
            run.pump(at - hold)
            check("leetcode_guard" in fleet.armed, "a weaker lock is armed first")
            fleet.launch(late)
            gone = run.pump(SHOW_S, lambda: "leetcode_guard" not in run.screen.shown())
            check(gone, "the weaker lock stepped back")
        order = _drive(run, check)
        check(not run.doubles, f"never two locks on screen (saw {run.doubles[:3]})")
        _say(f"order seen: {order}")
        _say("rank order" if order == list(_RANKED) else "NOT rank order")
    finally:
        fleet.stop()
        if helper.stdin:
            helper.stdin.close()
        helper.wait(timeout=10)
    _say("OK" if not failures else f"{len(failures)} FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "mixed"))
