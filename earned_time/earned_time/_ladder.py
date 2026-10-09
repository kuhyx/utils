# Copyright (c) 2026 Krzysztof Rudnicki
"""The shutdown ladder: from ``LADDER_FROM``, shutdown is read down from sleep.

The ceiling is ``WAKE_MINUTES`` minus eight hours (23:00 for a 07:00 wake);
the floor is that ceiling minus every earner's first-unit :class:`Rung`, so
doing everything lands exactly on the ceiling. Move the alarm and the whole
ladder moves with it. Days before ``LADDER_FROM`` keep their own values and a
frozen ceiling, so the switch never rewrites how an old day resolved. Gaming
is not on the ladder.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping

    from earned_time._policy import Earner

# The shutdown ceiling of every day before ``LADDER_FROM``. Frozen: a later
# ``WAKE_MINUTES`` change must not rewrite how an old day resolved.
SHUTDOWN_CEILING_MINUTES: Final = 23 * 60

# From this day shutdown follows the sleep ladder. A date, never a same-day
# cut: the day it was approved (2026-10-09) still resolves the old way.
LADDER_FROM: Final = date(2026, 10, 10)
# Alarm time, minutes after midnight. The ladder's ceiling is eight hours of
# sleep before it, so moving the alarm moves the whole ladder with it.
WAKE_MINUTES: Final = 7 * 60
_SLEEP_MINUTES: Final = 8 * 60
_DAY_MINUTES: Final = 24 * 60


@dataclass(frozen=True)
class Rung:
    """One earner's step on the shutdown ladder.

    Attributes:
        first: Shutdown minutes the first unit earns.
        extra: Each further unit (counted earners); the ladder pays none.
    """

    first: int
    extra: int = 0


# The rungs, keyed by earner name: they sum to the gap between the floor and
# the ceiling, so doing everything lands exactly on 23:00. A second workout
# earns nothing more.
LADDER: Final[Mapping[str, Rung]] = MappingProxyType(
    {
        "workout": Rung(110),
        "leetcode": Rung(50),
        "reading": Rung(30),
        "anki": Rung(25),
        "automation": Rung(25),
    }
)


def on_ladder(day: date) -> bool:
    """Whether ``day`` resolves shutdown on the sleep ladder."""
    return day >= LADDER_FROM


def _rung(item: Earner, day: date) -> Rung | None:
    return LADDER.get(item.name) if on_ladder(day) else None


def shutdown_minutes_for(item: Earner, day: date) -> int:
    """What ``item``'s first unit pushes shutdown later by on ``day``.

    Its ladder rung from ``LADDER_FROM`` on; before that, or for an earner
    without a rung, its own ``shutdown_minutes``.
    """
    rung = _rung(item, day)
    return item.shutdown_minutes if rung is None else rung.first


def extra_shutdown_minutes_for(item: Earner, day: date) -> int:
    """What each of ``item``'s further units earns on ``day`` (counted only)."""
    rung = _rung(item, day)
    return item.extra_shutdown_minutes if rung is None else rung.extra


def shutdown_ceiling_for(day: date) -> int:
    """The latest shutdown ``day`` can earn, minutes after its midnight."""
    if on_ladder(day):
        return _DAY_MINUTES + WAKE_MINUTES - _SLEEP_MINUTES
    return SHUTDOWN_CEILING_MINUTES
