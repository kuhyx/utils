# Copyright (c) 2026 Krzysztof Rudnicki
"""Adapter for ``activity.jsonl``: the timer and every heartbeat writer.

``timer`` events form segments ``start -> checkin ... -> stop``. A span
between two consecutive events counts only if the gap is at most
:data:`MAX_GAP_S`: a missed check-in stops the segment, and a late check-in
starts a fresh one. Time after the last check-in is not credited until the
next event vouches for it. Every other source (tutor, sql_drills, ...) is a
heartbeat covering the five minutes before it. Only events recorded for
``project`` count.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from focus_project._paths import activity_path
from focus_project.sources import Interval, heartbeat_interval

if TYPE_CHECKING:
    from datetime import date

    from focus_project._model import Project

MAX_GAP_S = 600.0
_LOG = logging.getLogger(__name__)


def read_events(project_id: str) -> list[dict[str, Any]]:
    """Well-formed events of ``project_id`` in time order; junk lines skipped."""
    try:
        text = activity_path().read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    events: list[dict[str, Any]] = []
    for line in text.splitlines():
        try:
            row = json.loads(line)
            ok = (
                isinstance(row, dict)
                and row.get("project") == project_id
                and isinstance(row["ts"], (int, float))
                and not isinstance(row["ts"], bool)
            )
        except ValueError, KeyError:
            ok = False
        if ok:
            events.append(row)
        elif line.strip():
            _LOG.debug("activity line skipped: %.80s", line)
    events.sort(key=lambda e: e["ts"])
    return events


def timer_intervals(events: list[dict[str, Any]]) -> list[Interval]:
    """Credited spans of the ``timer`` events (already time-ordered)."""
    spans: list[Interval] = []
    last: float | None = None  # the last event of the open segment
    for event in events:
        ts = float(event["ts"])
        kind = event.get("kind")
        if kind not in {"start", "checkin", "stop"}:
            continue
        if last is not None and ts - last <= MAX_GAP_S:
            spans.append((last, ts))
        last = None if kind == "stop" else ts
    return spans


def intervals(day: date, project: Project) -> list[Interval]:  # noqa: ARG001
    """Timer segments plus heartbeats of ``project`` (the registry clips)."""
    events = read_events(project.id)
    timer = [e for e in events if e.get("source") == "timer"]
    beats = [e for e in events if e.get("source") != "timer"]
    return [
        *timer_intervals(timer),
        *(heartbeat_interval(float(e["ts"])) for e in beats),
    ]
