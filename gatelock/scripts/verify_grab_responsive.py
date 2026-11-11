#!/usr/bin/env python3
# Copyright (c) 2026 Krzysztof Rudnicki
# pylint: disable=consider-using-with,import-error
r"""Prove the lock's Tk loop stays responsive while a foreign client holds the grab.

Tk's ``grab -global`` blocks the whole event loop for ~1.0 s on every FAILED
attempt, and the lock retries every 200 ms plus once a tick, so under a held
grab (2026-11-11: the keyring prompt) the loop was starved: no repaint, no
clicks, rows and buttons without text.

``prompt_grab_helper.py`` holds the grab (class ``steam_game``: not a prompt,
so no yielding muddies the measurement). A real ``mainloop`` runs for 5 s with
a 50 ms ``after`` heartbeat; the worst gap between beats must stay under
300 ms. After the helper lets go the lock must still take the grab.

    PYTHONPATH=. xvfb-run -a -s "-screen 0 1600x1200x24" \
        python3 scripts/verify_grab_responsive.py
"""

from __future__ import annotations

import os
from pathlib import Path
import select
import subprocess
import sys
import time
from unittest.mock import MagicMock

from gatelock import GateRoot, LockConfig, LockWindow
from gatelock._config import GrabPolicy

HELPER = Path(__file__).with_name("prompt_grab_helper.py")
BEAT_MS, RUN_S, MAX_GAP_S, WAIT_S = 50, 5.0, 0.3, 8.0


def _say(message: str) -> None:
    sys.stdout.write(f"{message}\n")


def _line(proc: subprocess.Popen[str]) -> str:
    out = proc.stdout
    ready = select.select([out], [], [], WAIT_S)[0] if out else []
    return out.readline().strip() if ready and out else ""


def _worst_gap(root: GateRoot) -> float:
    """Run the real mainloop for RUN_S; return the largest heartbeat gap."""
    last = [time.monotonic()]
    worst = [0.0]

    def beat() -> None:
        now = time.monotonic()
        worst[0] = max(worst[0], now - last[0])
        last[0] = now
        root.after(BEAT_MS, beat)

    root.after(BEAT_MS, beat)
    root.after(int(RUN_S * 1000), root.quit)
    root.mainloop()
    return worst[0]


def main() -> int:
    """Hold a foreign grab, measure the loop, then release; 0 when all held."""
    if os.environ.get("DISPLAY", "").split(".")[0] in {"", ":0"}:
        _say("refusing to run: DISPLAY must be a private X server, never :0")
        return 2
    helper = subprocess.Popen(
        [sys.executable, str(HELPER), "steam_game"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    failed = 0
    if _line(helper) != "READY":
        _say("FAIL helper did not take the grab")
        return 1
    root = GateRoot()
    config = LockConfig(mode="hard", grab=GrabPolicy(disable_vt=False, retry_ms=200))
    lock = LockWindow(root, config, MagicMock())
    try:
        lock.setup()
        lock.grab_input()
        gap = _worst_gap(root)
        ok = gap < MAX_GAP_S
        _say(f"{'PASS' if ok else 'FAIL'} worst loop gap {gap:.3f}s (< {MAX_GAP_S}s)")
        failed += not ok
        grab_held = lock.recovery.holds_grab()
        _say(f"{'FAIL' if grab_held else 'PASS'} helper still holds the grab")
        failed += grab_held
        if helper.stdin:
            helper.stdin.write("release\n")
            helper.stdin.flush()
        _line(helper)
        deadline = time.monotonic() + WAIT_S
        while time.monotonic() < deadline and not lock.recovery.holds_grab():
            root.update()
            time.sleep(0.05)
        got = lock.recovery.holds_grab()
        _say(f"{'PASS' if got else 'FAIL'} lock took the grab once it was free")
        failed += not got
    finally:
        lock.close()
        if helper.stdin:
            helper.stdin.close()
        helper.wait(timeout=WAIT_S)
    _say("OK" if not failed else f"{failed} FAILED")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
