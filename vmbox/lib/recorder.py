#!/usr/bin/env python3
"""Persistent QMP event recorder for a vmbox sandbox.

Started at VM launch, before anything runs inside the guest, and appends every
QMP event to a JSONL file. This ordering is the whole point: a guest that
powers itself off kills QEMU, so a prober attached *after* the fact finds a
closed socket and no event at all. Recording from launch means the verdict is
read from a file that outlives the VM.

Usage: recorder.py <qmp.sock> <events.jsonl>
"""

from __future__ import annotations

import json
import socket
import sys
import time
from typing import Any, TextIO


def connect(path: str, timeout: float = 30.0) -> socket.socket:
    """Connect to the QMP unix socket, retrying until QEMU creates it."""
    deadline = time.time() + timeout
    last_err: OSError | None = None
    while time.time() < deadline:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(path)
            return sock
        except OSError as exc:
            last_err = exc
            sock.close()
            time.sleep(0.1)
    raise SystemExit(f"recorder: could not connect to {path}: {last_err}")


def negotiate(stream: TextIO) -> None:
    """Complete the QMP capability handshake; events only flow afterwards."""
    stream.readline()  # greeting
    stream.write(json.dumps({"execute": "qmp_capabilities"}) + "\n")
    stream.flush()
    for _ in range(20):
        line = stream.readline()
        if not line:
            return
        msg = json.loads(line)
        if "return" in msg or "error" in msg:
            return


def record(stream: TextIO, out: TextIO) -> None:
    """Append each event as one JSON line, flushing so readers see it at once."""
    while True:
        line = stream.readline()
        if not line:  # QEMU exited: the guest is gone, which is itself a signal.
            _emit(out, {"event": "_RECORDER_EOF", "timestamp": _now()})
            return
        try:
            msg: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "event" in msg:
            _emit(out, msg)


def _now() -> dict[str, int]:
    now = time.time()
    return {"seconds": int(now), "microseconds": int((now % 1) * 1_000_000)}


def _emit(out: TextIO, msg: dict[str, Any]) -> None:
    out.write(json.dumps(msg) + "\n")
    out.flush()


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    qmp_path, events_path = sys.argv[1], sys.argv[2]

    sock = connect(qmp_path)
    # newline='\n' keeps QMP's line protocol intact regardless of locale.
    stream = sock.makefile("rw", encoding="utf-8", newline="\n")
    with open(events_path, "a", encoding="utf-8") as out:
        negotiate(stream)
        _emit(out, {"event": "_RECORDER_READY", "timestamp": _now()})
        try:
            record(stream, out)
        except OSError as exc:
            _emit(
                out,
                {
                    "event": "_RECORDER_ERROR",
                    "data": {"error": str(exc)},
                    "timestamp": _now(),
                },
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
