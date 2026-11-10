# Copyright (c) 2026 Krzysztof Rudnicki
"""Credited focus minutes per day: the union of every source's intervals.

Contract: union of activity intervals on the local calendar day plus the
overtime carried in from the day before (:mod:`focus_project.carry`), capped
at the active project's ``daily_minutes``; overlaps never double count; whole
minutes (floor). Time not yet lived is never credited: every interval is
clipped at "now", so an event stamped ahead of the clock (a fast phone clock)
earns only once the real clock reaches it. An unreadable registry reads as 0
(logged): fail closed.

Unbacked minutes (0.10.0): timer time the anti-cheat gate refused
(:mod:`focus_project.sources.activity`) and no other source covers, on the
local day up to "now"; carry and the cap play no part. Shown, never paid.
"""

from __future__ import annotations

from datetime import date  # noqa: TC003
import logging

from focus_project import _api, _clock, carry, sources
from focus_project._errors import RegistryError
from focus_project._own import union_seconds
from focus_project.sources import activity

_LOG = logging.getLogger(__name__)


def minutes_for(day: date, now: float | None = None) -> int:
    """Minutes of focus work credited on ``day`` (0 with no project active).

    ``now`` (default: the clock) is the moment after which nothing counts.
    """
    try:
        project = _api.active(day)
    except (RegistryError, OSError) as exc:
        _LOG.warning("focus_project registry unreadable, 0 minutes: %s", exc)
        return 0
    if project is None:
        return 0
    moment = _clock.now() if now is None else now
    return carry.balance(day, moment).counted(project.daily_on(day))


def unbacked_minutes_for(day: date, now: float | None = None) -> int:
    """Whole minutes of timer time on ``day`` that the gate did not count.

    0 with no project, before :data:`~focus_project.sources.activity.BACKING_FROM`,
    or with an unreadable registry (logged).
    """
    try:
        project = _api.active(day)
        if project is None:
            return 0
        lo, hi = sources.day_bounds(day)
        bounds = (lo, min(hi, _clock.now() if now is None else now))
        unbacked = sources.clip(activity.split_timer(day, project)[1], bounds)
        counted = sources.clip(sources.collect(day, project), bounds)
    except (RegistryError, OSError) as exc:
        _LOG.warning("focus_project registry unreadable, 0 unbacked: %s", exc)
        return 0
    # |unbacked minus counted| = |unbacked union counted| - |counted|.
    gap = union_seconds(unbacked + counted) - union_seconds(counted)
    return int(gap // 60)


__all__ = ["minutes_for", "unbacked_minutes_for", "union_seconds"]
