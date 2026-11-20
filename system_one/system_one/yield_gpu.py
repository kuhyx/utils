"""Stop the Kev model server the moment the GPU is wanted for something else.

Runs only while the model server runs (``PartOf`` + ``Wants`` in the units).
Every ``POLL_S`` it scans /proc for a game (no forks: ``guard.game_is_running``);
every ``VRAM_EVERY`` polls it also asks nvidia-smi how much VRAM OTHER
processes hold. Either trips -> ``systemctl --user stop`` the proxy and the
model, then exit. The next request then re-activates the socket, and
``kev_serve.sh``'s guard refuses to load while the game is still up.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

from system_one.guard import game_is_running, nvidia_smi, server_pids

POLL_S = float(os.environ.get("YIELD_POLL_S", "5"))
VRAM_EVERY = int(os.environ.get("YIELD_VRAM_EVERY", "6"))  # 6 x 5 s = 30 s
OTHER_VRAM_MIB = int(os.environ.get("YIELD_OTHER_VRAM_MIB", "5000"))
UNITS = ("system-one-kev.service", "system-one-kev-model.service")


def other_vram_mib(own: set[int]) -> int:
    """VRAM in use by everything except the model server.

    Total used minus the server's own compute allocation: games hold graphics
    contexts, which ``--query-compute-apps`` never lists, so only the total
    sees them. The desktop itself (Xorg, browser) is part of this figure.
    """
    used = nvidia_smi("--query-gpu=memory.used")
    if not used:
        return 0
    total = int(used[0].split(",")[0])
    for row in nvidia_smi("--query-compute-apps=pid,used_memory"):
        pid, mib = (int(x) for x in row.split(","))
        if pid in own:
            total -= mib
    return total


def reason_to_yield(tick: int) -> str:
    """Why the GPU should be given back now, or '' to keep serving."""
    if game_is_running():
        return "game running"
    if tick % VRAM_EVERY == 0:
        other = other_vram_mib(server_pids())
        if other > OTHER_VRAM_MIB:
            return f"other processes hold {other} MiB VRAM"
    return ""


def main() -> int:
    """Poll until a reason appears, then stop the units."""
    tick = 0
    while True:
        reason = reason_to_yield(tick)
        if reason:
            print(f"yield_gpu: {reason}; stopping Kev", file=sys.stderr)
            subprocess.run(["systemctl", "--user", "stop", *UNITS], check=False)
            return 0
        tick += 1
        time.sleep(POLL_S)


if __name__ == "__main__":
    raise SystemExit(main())
