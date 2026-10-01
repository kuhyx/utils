#!/usr/bin/env python3
"""Classify the last stop recorded in a vmbox QMP event log (events.jsonl).

Prints exactly one of:
  guest-shutdown  the guest powered itself off (ACPI S5)
  hibernate       the guest hibernated: QEMU emits SUSPEND_DISK right before
                  the SHUTDOWN when the guest enters ACPI S4
  guest-reset     the guest rebooted (-no-reboot turns that into a SHUTDOWN)
  panic           GUEST_PANICKED (pvpanic)
  host            a SHUTDOWN the guest did not initiate
  <reason>        any other SHUTDOWN reason, verbatim
  none            no stop at all

Usage: last_event.py <events.jsonl>
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable
from typing import Any


def _events(lines: Iterable[str]) -> Iterable[dict[str, Any]]:
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(msg, dict):
            yield msg


def classify(lines: Iterable[str]) -> str:
    """Return the kind of the LAST stop in the log (see module docstring)."""
    kind = "none"
    suspend_disk = False
    for msg in _events(lines):
        event = msg.get("event", "")
        if event == "GUEST_PANICKED":
            kind = "panic"
        elif event == "SUSPEND_DISK":
            # Only meaningful for the SHUTDOWN that follows it.
            suspend_disk = True
        elif event == "SHUTDOWN":
            data = msg.get("data", {})
            reason = data.get("reason", "")
            if not reason:
                reason = "guest-shutdown" if data.get("guest") else "host"
            kind = (
                "hibernate" if suspend_disk and reason == "guest-shutdown" else reason
            )
            suspend_disk = False
    return kind


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        with open(sys.argv[1], encoding="utf-8") as fh:
            print(classify(fh))
    except FileNotFoundError:
        print("none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
