#!/usr/bin/env python3
"""One-shot QMP client for vmbox: issue a command and print the reply.

Used for actions that need a round trip rather than passive event recording --
notably `screendump`, which is how locker/X11 tests get a screenshot without
any VNC or SPICE viewer installed on the host.

Usage:
  qmp.py <qmp.sock> screendump <out.png>
  qmp.py <qmp.sock> status
"""

from __future__ import annotations

import json
import os
import socket
import sys
from typing import Any, TextIO


def _open(path: str) -> tuple[socket.socket, TextIO]:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(20)
    sock.connect(path)
    stream = sock.makefile("rw", encoding="utf-8", newline="\n")
    stream.readline()  # greeting
    _command(stream, "qmp_capabilities")
    return sock, stream


def _command(stream: TextIO, name: str, **args: Any) -> dict[str, Any]:
    """Send one command and return its reply, skipping any events in between."""
    payload: dict[str, Any] = {"execute": name}
    if args:
        payload["arguments"] = args
    stream.write(json.dumps(payload) + "\n")
    stream.flush()
    while True:
        line = stream.readline()
        if not line:
            raise SystemExit(f"qmp: connection closed during '{name}'")
        msg = json.loads(line)
        if "return" in msg or "error" in msg:
            return msg


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    path, action = sys.argv[1], sys.argv[2]

    if not os.path.exists(path):
        print(f"qmp: no such socket: {path} (is the sandbox running?)", file=sys.stderr)
        return 1

    sock, stream = _open(path)
    try:
        if action == "screendump":
            if len(sys.argv) < 4:
                print("qmp: screendump needs an output path", file=sys.stderr)
                return 2
            out = os.path.abspath(sys.argv[3])
            # PNG is native to qemu's screendump; no ImageMagick needed.
            reply = _command(stream, "screendump", filename=out, format="png")
        elif action == "status":
            reply = _command(stream, "query-status")
        else:
            print(f"qmp: unknown action '{action}'", file=sys.stderr)
            return 2

        if "error" in reply:
            print(f"qmp: {reply['error'].get('desc', reply['error'])}", file=sys.stderr)
            return 1
        print(json.dumps(reply.get("return", {})))
        return 0
    finally:
        stream.close()
        sock.close()


if __name__ == "__main__":
    sys.exit(main())
