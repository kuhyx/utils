#!/usr/bin/env python3
# Copyright (c) 2026 Krzysztof Rudnicki
# pylint: disable=import-error
"""A second X client that holds the keyboard+pointer grab, like a credential prompt.

Started by ``verify_prompt_yield.py`` on a private display. Maps one window with
the given ``WM_CLASS`` (optionally inside an override-redirect frame, the way a
window manager reparents clients), takes ``XGrabKeyboard`` + ``XGrabPointer``,
prints ``READY``, then waits on stdin: ``release`` ungrabs and unmaps (prints
``RELEASED``), EOF exits.

Usage: ``prompt_grab_helper.py <wm_class> [--framed]``
"""

from __future__ import annotations

import sys
import time

from Xlib import X, display

OWNER_EVENTS = True
VIEWABLE_TRIES = 50


def main(argv: list[str]) -> int:
    """Grab, announce, wait for ``release``; returns a process exit status."""
    wm_class = argv[0]
    xdisplay = display.Display()
    root = xdisplay.screen().root
    depth = xdisplay.screen().root_depth
    top = window = root.create_window(
        10, 10, 400, 200, 0, depth, X.InputOutput, X.CopyFromParent
    )
    if "--framed" in argv:
        top = root.create_window(
            10, 10, 400, 200, 0, depth, X.InputOutput, X.CopyFromParent,
            override_redirect=1,
        )  # fmt: skip
        window.reparent(top, 0, 0)
    window.set_wm_class(wm_class, wm_class.capitalize())
    window.map()
    top.map()
    xdisplay.sync()
    # A window manager maps asynchronously; grabbing a not-yet-viewable window
    # fails with GrabNotViewable.
    for _ in range(VIEWABLE_TRIES):
        if window.get_attributes().map_state == X.IsViewable:
            break
        time.sleep(0.1)
    modes = (X.GrabModeAsync, X.GrabModeAsync)
    keyboard = window.grab_keyboard(OWNER_EVENTS, *modes, X.CurrentTime)
    pointer = window.grab_pointer(
        OWNER_EVENTS, X.ButtonPressMask, *modes, X.NONE, X.NONE, X.CurrentTime
    )
    if keyboard or pointer:
        sys.stdout.write(f"grab failed keyboard={keyboard} pointer={pointer}\n")
        return 2
    sys.stdout.write("READY\n")
    sys.stdout.flush()
    for line in sys.stdin:
        if line.strip() == "release":
            xdisplay.ungrab_keyboard(X.CurrentTime)
            xdisplay.ungrab_pointer(X.CurrentTime)
            top.unmap()
            xdisplay.sync()
            sys.stdout.write("RELEASED\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
