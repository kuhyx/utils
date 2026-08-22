#!/usr/bin/env python3
"""Run a command in a vmbox guest over its serial console root shell.

This exists because ssh is not the right channel for the thing vmbox is for.
A shutdown script kills the connection carrying its own result, and the serial
console keeps printing right through the poweroff -- so for the shutdown case
serial is not a fallback, it is the better transport. It also works when sshd
is broken, which makes an unreachable guest debuggable instead of opaque.

Every command is bracketed by explicit markers and waited on until its END
marker appears. Never use a fixed sleep: if the window closes early the next
command is typed while the previous one still runs, the tty echoes that input,
and the echoed text is indistinguishable from output in the transcript.

Usage:
  serial_exec.py <console.sock> <command>            -> runs, prints output
  serial_exec.py <console.sock> --wait-prompt        -> just wait for a shell
"""

from __future__ import annotations

import re
import socket
import sys
import time
import uuid

PROMPT = "[root@vmbox"
# Strip ANSI CSI sequences and the OSC 3008 shell-integration blocks that
# systemd's login emits, both of which otherwise corrupt marker matching.
_ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")
_OSC = re.compile(r"\x1b?\]3008;[^\x07\\]*(?:\x07|\\)?")


def clean(raw: bytes) -> str:
    text = raw.decode("utf-8", "replace")
    text = _ANSI.sub("", text)
    text = _OSC.sub("", text)
    return text.replace("\r", "")


class Console:
    """A line-oriented client for the guest's serial console socket."""

    def __init__(self, path: str) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(path)
        self.sock.settimeout(0.4)
        self.buf = b""

    def read_until(self, needle: str, timeout: float) -> bool:
        end = time.time() + timeout
        while time.time() < end:
            try:
                chunk = self.sock.recv(4096)
            except TimeoutError:
                continue
            except OSError:
                return False
            if not chunk:
                return False
            self.buf += chunk
            if needle in clean(self.buf):
                return True
        return False

    def wait_prompt(self, timeout: float = 180) -> bool:
        # Nudge with a newline: if the shell is already up we get a fresh
        # prompt immediately instead of waiting for unrelated output.
        self.sock.sendall(b"\n")
        return self.read_until(PROMPT, timeout)

    def read_until_count(self, needle: str, count: int, timeout: float) -> bool:
        """Wait until `needle` has been seen `count` times.

        A tty echoes what you type, so the marker appears once in the echoed
        command line before it ever appears in real output. Waiting for the
        first occurrence returns immediately -- before the command has run --
        and yields an empty or truncated result that looks like a hang.
        """
        end = time.time() + timeout
        while time.time() < end:
            if clean(self.buf).count(needle) >= count:
                return True
            try:
                chunk = self.sock.recv(4096)
            except TimeoutError:
                continue
            except OSError:
                return False
            if not chunk:
                return False
            self.buf += chunk
        return clean(self.buf).count(needle) >= count

    def run(self, cmd: str, timeout: float = 300) -> str:
        # Markers are plain alphanumerics: shell metacharacters like < and >
        # are echoed back by the tty and can be reordered or line-wrapped,
        # which makes them unreliable to match on.
        token = uuid.uuid4().hex[:8].upper()
        start, done = f"VMBOXS{token}", f"VMBOXE{token}"
        self.buf = b""
        # `; echo RC=$?` keeps the guest's exit status, which the ssh path
        # cannot report once the machine stops.
        self.sock.sendall(f"echo {start}; {cmd}; echo RC=$?; echo {done}\n".encode())
        # Twice: once in the echoed command line, once in real output.
        if not self.read_until_count(done, 2, timeout):
            return f"### TIMEOUT: no end marker after {timeout}s ###"
        text = clean(self.buf)
        # Take the LAST start marker and the text up to the following end
        # marker: everything before that is the echo of what we typed.
        body = text.rsplit(start, 1)[-1].split(done, 1)[0]
        lines = [ln for ln in body.splitlines() if start not in ln and done not in ln]
        return "\n".join(lines).strip()


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    console = Console(sys.argv[1])
    if sys.argv[2] == "--wait-prompt":
        return 0 if console.wait_prompt() else 1
    if not console.wait_prompt():
        print("serial_exec: no root prompt on the console", file=sys.stderr)
        return 1
    print(console.run(" ".join(sys.argv[2:])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
