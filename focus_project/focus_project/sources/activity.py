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

0.10.0 anti-cheat (days from :data:`BACKING_FROM`): a timer span earns only
if real activity of the same project backs it, whole span or nothing. A
backing event is a ``tutor``/``sql_drills``/``leetcode`` heartbeat or an
accepted LeetCode submission (leetcode projects only); ``browser`` never
backs. A span ``(a, b)`` is backed if a backing event lies in
``[a - 300, b]``, or between two consecutive backing events at most
:data:`BRIDGE_S` apart. Check-ins alone earn 0. Earlier days keep the old
rule (every span counts), so paid days never change.
"""

from __future__ import annotations

from datetime import date
import importlib
from itertools import pairwise
import json
import logging
from typing import TYPE_CHECKING, Any, Final

from focus_project._paths import activity_path
from focus_project.sources import HEARTBEAT_WINDOW_S, Interval, heartbeat_interval

if TYPE_CHECKING:
    from focus_project._model import Project

MAX_GAP_S = 600.0
BACKING_FROM: Final = date(2026, 11, 8)
BACKING_SOURCES: Final = frozenset({"tutor", "sql_drills", "leetcode"})
BRIDGE_S: Final = 1200.0
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


def backing_times(events: list[dict[str, Any]], project: Project) -> list[float]:
    """Sorted times of the events that may back a timer span.

    The LeetCode ledger is read in its own guard: if it fails, only the
    submissions are lost, never the heartbeats (fail closed, narrow).
    """
    times = [float(e["ts"]) for e in events if e.get("source") in BACKING_SOURCES]
    try:
        # Imported lazily: it pulls in earned_time, and the timer must keep
        # working (heartbeat backing only) where that is not installed.
        leetcode = importlib.import_module("focus_project.sources.leetcode")
        times += leetcode.submission_times(project)
    except Exception:  # noqa: BLE001 (lose the submissions, keep the beats)
        _LOG.exception("leetcode backing unavailable, heartbeats only")
    return sorted(times)


def is_backed(span: Interval, times: list[float]) -> bool:
    """Whether a backing event lies in or just before ``span``, or bridges it."""
    lo, hi = span
    if any(lo - HEARTBEAT_WINDOW_S <= t <= hi for t in times):
        return True
    return any(a <= lo and hi <= b and b - a <= BRIDGE_S for a, b in pairwise(times))


def split_timer(
    day: date, project: Project, events: list[dict[str, Any]] | None = None
) -> tuple[list[Interval], list[Interval]]:
    """``(backed, unbacked)`` timer spans of ``project``, judged for ``day``."""
    found = read_events(project.id) if events is None else events
    chain = [e for e in found if e.get("source") == "timer" or _is_beat(e)]
    spans = timer_intervals(chain)
    if day < BACKING_FROM:
        return spans, []
    times = backing_times(found, project)
    backed = [s for s in spans if is_backed(s, times)]
    return backed, [s for s in spans if s not in backed]


def intervals(day: date, project: Project) -> list[Interval]:
    """Backed timer segments plus heartbeats of ``project`` (the registry clips)."""
    events = read_events(project.id)
    beats = [e for e in events if e.get("source") != "timer"]
    return [
        *split_timer(day, project, events)[0],
        *(heartbeat_interval(float(e["ts"])) for e in beats),
    ]
