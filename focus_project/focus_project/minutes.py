# Copyright (c) 2026 Krzysztof Rudnicki
"""Credited focus minutes per day: the union of every source's intervals.

Contract: union of activity intervals on the local calendar day plus the
overtime carried in from the day before (:mod:`focus_project.carry`), capped
at the active project's ``daily_minutes``; overlaps never double count; whole
minutes (floor). Time not yet lived is never credited: every interval is
clipped at "now", so an event stamped ahead of the clock (a fast phone clock)
earns only once the real clock reaches it. An unreadable registry reads as 0
(logged): fail closed.
"""

from __future__ import annotations

from datetime import date  # noqa: TC003
import logging

from focus_project import _api, _clock, carry
from focus_project._errors import RegistryError
from focus_project._own import union_seconds

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


__all__ = ["minutes_for", "union_seconds"]
