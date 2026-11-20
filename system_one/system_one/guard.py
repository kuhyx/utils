"""May a local decision model use the GPU right now?

Two conditions, checked by the CLIENT before it connects (opening the
socket-activated port is what loads the model, so the check cannot live in the
server):

1. No game is running. Same two predicates steam-backlog-enforcer bills
   playtime by: ``SteamAppId`` != 0 in a process environment (an idle Steam
   client does not count), or a process whose ``comm`` is one of the
   enforcer's ``counted_processes`` (non-Steam games; default osu!lazer).
2. Enough free VRAM for the model, where memory the model server ALREADY holds
   counts as available (a warm Kev must not lock itself out).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

PROC = Path("/proc")
ENFORCER_CONFIG = Path.home() / ".config" / "steam_backlog_enforcer" / "config.json"
# Mirrors steam_backlog_enforcer._counted_procs.DEFAULT_COUNTED_PROCESSES.
DEFAULT_GAME_NAMES = frozenset({"osu-lazer", "osu.AppImage", "osu!"})


def native_game_names(config: Path = ENFORCER_CONFIG) -> frozenset[str]:
    """The enforcer's counted non-Steam process names (defaults if unreadable)."""
    try:
        entries = json.loads(config.read_text()).get("counted_processes")
    except (OSError, ValueError, AttributeError):
        return DEFAULT_GAME_NAMES
    if not isinstance(entries, list):
        return DEFAULT_GAME_NAMES
    names = {
        str(n)
        for e in entries
        if isinstance(e, dict) and isinstance(e.get("names"), list)
        for n in e["names"]
    }
    return frozenset(names) or DEFAULT_GAME_NAMES


def _steam_game(env: bytes) -> bool:
    return any(
        var.startswith(b"SteamAppId=") and var[11:] not in {b"", b"0"}
        for var in env.split(b"\0")
    )


def game_is_running(proc: Path = PROC, names: frozenset[str] | None = None) -> bool:
    """Whether a Steam game or a counted native game is running."""
    names = native_game_names() if names is None else names
    # comm is truncated to 15 bytes by the kernel; compare truncated names too.
    short = {n[:15] for n in names}
    for pid_dir in proc.glob("[0-9]*"):
        try:
            if (pid_dir / "comm").read_text().strip() in short:
                return True
            if _steam_game((pid_dir / "environ").read_bytes()):
                return True
        except OSError:  # gone, or another user's process
            continue
    return False


def nvidia_smi(*args: str) -> list[str]:
    exe = shutil.which("nvidia-smi")
    if exe is None:
        return []
    try:
        out = subprocess.run(
            [exe, *args, "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def free_vram_mib(server_pids: set[int] | None = None) -> int:
    """Free VRAM on GPU 0 plus whatever ``server_pids`` already hold; 0 if unknown."""
    rows = nvidia_smi("--query-gpu=memory.free")
    if not rows:
        return 0
    free = int(rows[0].split(",")[0])
    if server_pids:
        for row in nvidia_smi("--query-compute-apps=pid,used_memory"):
            pid, used = (int(x) for x in row.split(","))
            if pid in server_pids:
                free += used
    return free


SERVER_MARKERS = (b"kev.serve", b"kev_launch.py")


def server_pids(markers: tuple[bytes, ...] = SERVER_MARKERS) -> set[int]:
    """PIDs of the model server (plain ``-m kev.serve`` or via kev_launch.py)."""
    pids: set[int] = set()
    for cmd in PROC.glob("[0-9]*/cmdline"):
        try:
            line = cmd.read_bytes()
            if any(m in line for m in markers):
                pids.add(int(cmd.parent.name))
        except OSError:
            continue
    return pids


def main(argv: list[str] | None = None) -> int:
    """``python -m system_one.guard NEED_MIB``: exit 0 if the GPU may be used."""
    args = sys.argv[1:] if argv is None else argv
    ok, reason = gpu_available(int(args[0]) if args else 16000)
    print(f"system_one.guard: {reason}", file=sys.stderr)
    return 0 if ok else 1


def gpu_available(need_mib: int) -> tuple[bool, str]:
    """(ok, reason). ``ok`` is False while gaming or short of VRAM."""
    if game_is_running():
        return False, "game running"
    free = free_vram_mib(server_pids())
    if free < need_mib:
        return False, f"free VRAM {free} MiB < {need_mib} MiB"
    return True, "ok"


if __name__ == "__main__":
    raise SystemExit(main())
