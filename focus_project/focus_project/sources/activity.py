# Copyright (c) 2026 Krzysztof Rudnicki
"""Adapter for ``activity.jsonl``: the timer and every heartbeat writer.

``timer`` events form segments ``start -> checkin ... -> stop``. A span
between two consecutive events counts only if the gap is at most
:data:`MAX_GAP_S`: a missed check-in stops the segment, and a late check-in
starts a fresh one. Time after the last check-in is not credited until the
next event vouches for it. Every other source (tutor, sql_drills, ...) is a
heartbeat covering the five minutes before it. Only events recorded for
``project`` count.

0.8.0: a ``tutor`` ``heartbeat`` (a graded check-in card) is also a beat of
the open segment, like a ``checkin``: within :data:`MAX_GAP_S` of the last
beat it extends the segment; later it ends the segment at that last beat. It
never opens a segment. Other heartbeat sources never chain the timer.
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
    """Credited spans of the ``timer`` events and tutor beats (time-ordered)."""
    spans: list[Interval] = []
    last: float | None = None  # the last beat of the open segment
    for event in events:
        ts = float(event["ts"])
        kind = event.get("kind")
        beat = _is_beat(event)
        if not beat and kind not in {"start", "checkin", "stop"}:
            continue
        on_time = False
        if last is not None and ts - last <= MAX_GAP_S:
            spans.append((last, ts))
            on_time = True
        # A beat never opens a segment; a stop closes it; start/checkin open it.
        keep = on_time if beat else kind != "stop"
        last = ts if keep else None
    return spans


def _is_beat(event: dict[str, Any]) -> bool:
    """A tutor heartbeat: it chains the timer segment (0.8.0)."""
    return event.get("source") == "tutor" and event.get("kind") == "heartbeat"


def sessions(project_id: str) -> list[Interval]:
    """Contiguous focus sessions of ``project_id``, time-ordered, as (start, end).

    Built from the same timer/tutor-beat segments (and so the same
    :data:`MAX_GAP_S` rule) that credit minutes; spans that touch are one
    session, which ends at its last beat.
    """
    events = read_events(project_id)
    timer = [e for e in events if e.get("source") == "timer" or _is_beat(e)]
    merged: list[Interval] = []
    for lo, hi in timer_intervals(timer):
        if merged and lo <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(hi, merged[-1][1]))
        else:
            merged.append((lo, hi))
    return merged


def intervals(day: date, project: Project) -> list[Interval]:  # noqa: ARG001
    """Timer segments plus heartbeats of ``project`` (the registry clips)."""
    events = read_events(project.id)
    timer = [e for e in events if e.get("source") == "timer" or _is_beat(e)]
    beats = [e for e in events if e.get("source") != "timer"]
    return [
        *timer_intervals(timer),
        *(heartbeat_interval(float(e["ts"])) for e in beats),
    ]
