# Copyright (c) 2026 Krzysztof Rudnicki
"""Credited focus minutes per day: the union of every source's intervals.

Contract: union of activity intervals on the local calendar day, capped at
the active project's ``daily_minutes``; overlaps never double count; whole
minutes (floor). An unreadable registry reads as 0 (logged): fail closed.
"""

from __future__ import annotations

from datetime import date  # noqa: TC003
import logging

from focus_project import _api, sources
from focus_project._errors import RegistryError

_LOG = logging.getLogger(__name__)


def union_seconds(spans: list[sources.Interval]) -> float:
    """Total length of the union of ``spans``."""
    total = 0.0
    end = float("-inf")
    for lo, hi in sorted(spans):
        if hi <= end:
            continue
        total += hi - max(lo, end)
        end = hi
    return total


def minutes_for(day: date) -> int:
    """Minutes of focus work credited on ``day`` (0 with no project active)."""
    try:
        project = _api.active(day)
    except (RegistryError, OSError) as exc:
        _LOG.warning("focus_project registry unreadable, 0 minutes: %s", exc)
        return 0
    if project is None:
        return 0
    seconds = union_seconds(sources.collect(day, project))
    return min(int(seconds // 60), project.daily_on(day))
