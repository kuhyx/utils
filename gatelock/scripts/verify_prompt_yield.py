#!/usr/bin/env python3
# Copyright (c) 2026 Krzysztof Rudnicki
# pylint: disable=missing-function-docstring,consider-using-with,import-error
r"""Prove, on a real X server, that the lock yields to a system credential prompt.

No unit test can: in the suite the Tk root is a MagicMock, so the grab never
fails and stacking is never real. The 2026-11-11 incident was exactly that.

``prompt_grab_helper.py`` (a second X client, so Tk really answers "another
application has grab") maps a window with a chosen ``WM_CLASS`` and takes the
keyboard+pointer grab; a ``LockWindow`` then arms over it. Cases: ``prompt``
(gcr-prompter must end up above backdrop and surfaces, stay there, and the lock
must retake the grab and the top once the helper lets go), ``framed`` (client
inside an override-redirect frame, like i3: the top-level ancestor is raised),
``game`` (steam_game is not allowlisted: lock stays on top), ``i3`` (like
``prompt`` under a real i3 with a private runtime dir).

Run one case on a throwaway display (never ``:0``)::

    PYTHONPATH=. xvfb-run -a -s "-screen 0 1600x1200x24" \
        python3 scripts/verify_prompt_yield.py prompt
"""

from __future__ import annotations

import _tkinter
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import time
import tkinter as tk
from typing import TYPE_CHECKING, Final
from unittest.mock import MagicMock

from Xlib import X, display

from gatelock import GateRoot, LockConfig, LockWindow
from gatelock._config import GrabPolicy

if TYPE_CHECKING:
    from collections.abc import Callable

HELPER: Final = Path(__file__).with_name("prompt_grab_helper.py")
CASES: Final = {  # case -> (WM_CLASS instance, framed)
    "prompt": ("gcr-prompter", False),
    "framed": ("gcr-prompter", True),
    "game": ("steam_game", False),
    "i3": ("gcr-prompter", False),
}
STEP_S, WAIT_S = 0.05, 8.0


def _say(message: str) -> None:
    sys.stdout.write(f"{message}\n")


class _Helper:
    """The grab-holding subprocess, as seen from the checking side."""

    def __init__(self, wm_class: str, *, framed: bool) -> None:
        args = [sys.executable, str(HELPER), wm_class, *(["--framed"] * framed)]
        self.proc = subprocess.Popen(
            args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
        )
        self._expect("READY")

    def _expect(self, word: str) -> None:
        out = self.proc.stdout
        ready = select.select([out], [], [], WAIT_S)[0] if out else []
        line = out.readline().strip() if ready and out else ""
        if line != word:
            msg = f"helper said {line!r}, wanted {word!r}"
            raise RuntimeError(msg)

    def release(self) -> None:
        if self.proc.stdin:
            self.proc.stdin.write("release\n")
            self.proc.stdin.flush()
        self._expect("RELEASED")

    def stop(self) -> None:
        if self.proc.stdin:
            self.proc.stdin.close()
        self.proc.wait(timeout=WAIT_S)


class _Stack:
    """Real stacking order, read over the harness's own X connection."""

    def __init__(self, lock_tops: list[int]) -> None:
        self.display = display.Display()
        self.root = self.display.screen().root
        self.lock_ids = [self.top_of(i) for i in lock_tops]
        self.prompt = 0

    def top_of(self, window_id: int) -> int:
        win = self.display.create_resource_object("window", window_id)
        while (parent := win.query_tree().parent).id != self.root.id:
            win = parent
        return int(win.id)

    def order(self) -> list[int]:
        return [w.id for w in self.root.query_tree().children]

    def viewable(self, window_id: int) -> bool:
        win = self.display.create_resource_object("window", window_id)
        return bool(win.get_attributes().map_state == X.IsViewable)

    def find(self, wm_class: str) -> int | None:
        """The root child that is, or contains, the helper's window."""
        for child in self.root.query_tree().children:
            for win in (child, *child.query_tree().children):
                found = win.get_wm_class()
                if found and found[0] == wm_class:
                    self.prompt = int(child.id)
                    return self.prompt
        return None

    def covered(self) -> bool:
        order = self.order()
        return all(order.index(i) > order.index(self.prompt) for i in self.lock_ids)

    def on_top(self) -> bool:
        order = self.order()
        return all(order.index(self.prompt) > order.index(i) for i in self.lock_ids)

    def lock_topmost(self) -> bool:
        """The topmost *viewable* root child belongs to the lock."""
        top = next(i for i in reversed(self.order()) if self.viewable(i))
        return top in self.lock_ids


def _pump(root: tk.Tk, seconds: float, until: Callable[[], bool] | None = None) -> bool:
    """Run Tk's event loop for ``seconds`` or until ``until`` holds.

    One event at a time: ``update()`` never returns while the lock's grab
    retries (each blocks Tk for ~1 s) keep coming due.
    """
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        root.tk.dooneevent(_tkinter.DONT_WAIT)
        if until is not None and until():
            return True
        time.sleep(STEP_S)
    return until() if until is not None else False


def _start_i3() -> subprocess.Popen[bytes]:
    """Start i3 on the private display, with a private runtime dir."""
    home = Path(tempfile.mkdtemp(prefix="gl-i3-"))
    (home / "config").write_text("font pango:monospace 8\n", encoding="utf-8")
    # No inherited I3SOCK: this i3 must never touch the live session's socket.
    env = {k: v for k, v in os.environ.items() if k != "I3SOCK"}
    env["XDG_RUNTIME_DIR"] = str(home)
    proc = subprocess.Popen(["/usr/bin/i3", "-c", str(home / "config")], env=env)
    probe = display.Display()
    atom = probe.intern_atom("I3_SOCKET_PATH")
    deadline = time.monotonic() + WAIT_S
    while time.monotonic() < deadline:
        if probe.screen().root.get_full_property(atom, X.AnyPropertyType):
            return proc
        time.sleep(0.1)
    proc.kill()
    msg = "i3 never came up"
    raise RuntimeError(msg)


def _checks(case: str, root: tk.Tk, lock: LockWindow, helper: _Helper) -> list[str]:
    """Drive the armed lock through one scenario; returns failed labels."""
    wm_class = CASES[case][0]
    failures: list[str] = []

    def check(ok: object, label: str) -> None:
        _say(f"{'PASS' if ok else 'FAIL'} {label}")
        if not ok:
            failures.append(label)

    _pump(root, 0.3)
    tops: list[tk.Wm] = [root]
    tops += [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
    seen = _Stack([int(t.wm_frame(), 16) for t in tops])
    prompt = seen.find(wm_class)
    check(prompt is not None, "helper window found on the root")
    if prompt is None:
        return failures
    _pump(root, 0.7)
    check(seen.covered(), "t<1s: lock starts above the prompt (incident)")
    check(not lock.recovery.holds_grab(), "t<1s: the helper holds the grab")
    yielded = _pump(root, WAIT_S, seen.on_top)
    if case == "game":
        check(not yielded, "steam_game: lock stays on top (no yield)")
        _pump(root, 2.5)
        check(seen.covered(), "steam_game: still covered 2.5s later")
    else:
        check(yielded, "prompt raised above backdrop and every surface")
        _pump(root, 2.5)  # several enforce ticks
        check(seen.on_top(), "prompt stays on top across ticks")
        check(not lock.recovery.holds_grab(), "lock does not hold the grab yet")
        check(all(seen.viewable(i) for i in seen.lock_ids), "lock still mapped")
    helper.release()
    got = _pump(root, WAIT_S, lock.recovery.holds_grab)
    check(got, "after the helper let go, the lock took the grab")
    _pump(root, 1.5)
    check(seen.lock_topmost(), "lock is back on top of everything viewable")
    return failures


def _run_case(case: str) -> list[str]:
    """Arm a lock over the helper's grab, run the scenario, tear it all down."""
    wm_class, framed = CASES[case]
    wm = _start_i3() if case == "i3" else None
    helper = lock = None
    try:
        helper = _Helper(wm_class, framed=framed)
        root = GateRoot()
        config = LockConfig(
            mode="hard", grab=GrabPolicy(disable_vt=False, retry_ms=200)
        )
        lock = LockWindow(root, config, MagicMock())
        lock.setup()
        lock.grab_input()
        return _checks(case, root, lock, helper)
    finally:
        if lock is not None:
            lock.close()
        if helper is not None:
            helper.stop()
        if wm is not None:
            wm.terminate()


def main(argv: list[str]) -> int:
    """Run the named case on a private display; 0 when every check held."""
    xdisplay = os.environ.get("DISPLAY", "")
    if not xdisplay or xdisplay.split(".")[0] == ":0":
        _say("refusing to run: DISPLAY must be a private X server, never :0")
        return 2
    if len(argv) != 1 or argv[0] not in CASES:
        _say(f"usage: verify_prompt_yield.py {{{'|'.join(CASES)}}}")
        return 2
    failed = _run_case(argv[0])
    _say("OK" if not failed else f"{len(failed)} FAILED")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
