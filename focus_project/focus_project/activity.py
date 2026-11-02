# Copyright (c) 2026 Krzysztof Rudnicki
"""Append-only activity.jsonl; one flock'd, fsync'd line per event."""

from __future__ import annotations

from datetime import date
import fcntl
import json
import os
import time
from typing import Any

from focus_project import _api
from focus_project._paths import activity_path, data_dir

SOURCES = frozenset({"timer", "tutor", "sql_drills", "leetcode", "browser"})
KINDS = frozenset({"start", "checkin", "stop", "heartbeat"})
DEVICES = frozenset({"pc", "phone"})


def record_activity(  # noqa: PLR0913, PLR0917
    source: str,
    kind: str,
    ts: float | None = None,
    project: str | None = None,
    dev: str = "pc",
    meta: dict[str, Any] | None = None,
) -> None:
    """Append one event. ``project`` defaults to the project active at ``ts``."""
    for value, allowed, label in (
        (source, SOURCES, "source"),
        (kind, KINDS, "kind"),
        (dev, DEVICES, "dev"),
    ):
        if value not in allowed:
            msg = f"unknown {label} {value!r}; expected one of {sorted(allowed)}"
            raise ValueError(msg)
    when = time.time() if ts is None else ts
    if project is None:
        found = _api.active(date.fromtimestamp(when))  # noqa: DTZ012
        project = found.id if found else None
    line = json.dumps(
        {
            "ts": when,
            "source": source,
            "kind": kind,
            "project": project,
            "dev": dev,
            "meta": meta or {},
        },
        separators=(",", ":"),
    )
    data_dir().mkdir(parents=True, exist_ok=True)
    with activity_path().open("a", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())
