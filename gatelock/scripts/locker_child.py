#!/usr/bin/env python3
# Copyright (c) 2026 Krzysztof Rudnicki
# pylint: disable=missing-function-docstring
"""One stand-in locker for ``verify_all_lockers.py``: the real startup sequence.

Mirrors what leetcode_guard / screen_locker / diet_guard / book_guard /
focus_guard do: ``Arbiter`` -> ``publish`` -> ``wait_for_turn`` (windowless) ->
``acquire_holder`` -> ``LockWindow`` -> ``setup`` -> ``grab_input`` -> mainloop,
with the real app name and rank. Its only UI is one button; clicking it ends
the lock, like a solve does. Everything is reported on stdout, one line each:
``ARMED``, ``BTN x y`` (button centre, root coordinates), ``GRAB 0|1``,
``CLICKED``.

Usage: ``locker_child.py <app> <rank> <queue_poll_s>``
"""

from __future__ import annotations

import sys
import tkinter as tk

from gatelock import (
    Arbiter,
    GateRoot,
    LockConfig,
    LockWindow,
    wait_for_turn,
)

REPORT_MS = 250


class _Child:
    """The hooks object, as each real locker is."""

    def __init__(self, app: str, rank: int, poll: float) -> None:
        self.app = app
        self.button: tk.Button | None = None
        config = LockConfig(mode="hard", app_name=app, rank=rank)
        arbiter = Arbiter(
            app,
            rank,
            grab=config.resolved_grab(),
            disable_vt=False,
        )
        arbiter.publish()
        wait_for_turn(arbiter, poll=poll)
        arbiter.acquire_holder()
        self.root = GateRoot(className=app)
        self.lock = LockWindow(self.root, config, self, arbiter=arbiter)
        self.lock.setup()
        self.say("ARMED")
        self.lock.grab_input()
        self.root.after(REPORT_MS, self.report)

    def say(self, text: str) -> None:
        sys.stdout.write(f"{text}\n")
        sys.stdout.flush()

    def report(self) -> None:
        self.say(f"GRAB {int(self.lock.recovery.holds_grab())}")
        button = self.button
        if button is not None and button.winfo_ismapped():
            x = button.winfo_rootx() + button.winfo_width() // 2
            y = button.winfo_rooty() + button.winfo_height() // 2
            self.say(f"BTN {x} {y}")
        self.root.after(REPORT_MS, self.report)

    def clicked(self) -> None:
        self.say("CLICKED")
        self.lock.close()

    # -- LockWindowHooks ---------------------------------------------------
    def build_surface(self, parent: tk.Misc, surface: object) -> None:
        del surface
        self.button = tk.Button(parent, text=self.app, command=self.clicked)
        self.button.place(relx=0.5, rely=0.5, width=240, height=90, anchor="center")

    def teardown_surface(self, surface: object) -> None:
        del surface
        self.button = None

    def on_focus_ready(self, surface: object) -> None:
        del surface

    def on_callback_error(self) -> None:
        self.say("ERROR callback")

    def on_close(self) -> None:
        return


def main(argv: list[str]) -> int:
    """Arm one locker and run its mainloop."""
    child = _Child(argv[0], int(argv[1]), float(argv[2]))
    child.lock.run()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
