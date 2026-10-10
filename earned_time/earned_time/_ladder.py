# Copyright (c) 2026 Krzysztof Rudnicki
"""The shutdown ladder: from ``LADDER_FROM``, shutdown is read down from sleep.

The ceiling is ``WAKE_MINUTES`` minus eight hours (23:00 for a 07:00 wake);
the floor is that ceiling minus every earner's first-unit :class:`Rung`, so
doing everything lands exactly on the ceiling. Move the alarm and the whole
ladder moves with it. Days before ``LADDER_FROM`` keep their own values and a
frozen ceiling, so the switch never rewrites how an old day resolved. Gaming
is not on the ladder.

From ``TUTOR_FROM`` the rungs are :data:`TUTOR_LADDER`: Anki is retired and
its 25 minutes fold into the Automation tutor's, paid per 15-minute block.
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
# From this day the Anki earner is retired and Automation is paid per tutor
# block (``earned_time._policy.AUTOMATION_TUTOR``). The day after the deploy
# (0.6.1, 2026-10-09) -- never the deploy day itself (a same-day cut,
# 2026-09-26). Confirmed in 0.7.0 (``confirmed_on`` 2026-10-09, kuhy's call
# on 2026-10-10), so its penalty bites from this day on.
TUTOR_FROM: Final = date(2026, 10, 10)
# From this day until TUTOR_FROM the Anki and old Automation earners are
# waived: neither penalised nor paid, since both are being retired and the
# tutor that replaces them is not yet confirmed. Raise-only on every day (the
# floor rises by exactly what the two could have paid back), so it may land
# on its deploy day: 0.5.0 landed 2026-10-09.
ANKI_WAIVED_FROM: Final = date(2026, 10, 9)
_SLEEP_MINUTES: Final = 8 * 60
_DAY_MINUTES: Final = 24 * 60


@dataclass(frozen=True)
class Rung:
    """One earner's step on the shutdown ladder.

    Attributes:
        first: Shutdown minutes the first unit earns.
        extra: Each further unit (counted earners) once ``steps`` run out.
        steps: What the second, third, ... unit earn, in order, when they are
            not all the same.
    """

    first: int
    extra: int = 0
    steps: tuple[int, ...] = ()

    @property
    def second(self) -> int:
        """What the second unit earns."""
        return self.steps[0] if self.steps else self.extra

    def minutes(self, units: int) -> int:
        """Shutdown minutes ``units`` earn on this rung (``0`` for none)."""
        if units <= 0:
            return 0
        further = units - 1
        listed = sum(self.steps[:further])
        return self.first + listed + max(0, further - len(self.steps)) * self.extra


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


# From ``TUTOR_FROM``: Anki's 25 folded into Automation's, which is paid per
# 15-minute tutor block. Each block earns the 15 minutes it costs (the fairness
# rule; 13/13/12/12 paid 50 for 60 sat), so the rungs sum to 250: doing
# everything is still 23:00, doing nothing 18:50.
TUTOR_LADDER: Final[Mapping[str, Rung]] = MappingProxyType(
    {
        "workout": Rung(110),
        "leetcode": Rung(50),
        "reading": Rung(30),
        "automation": Rung(15, extra=15),
    }
)


def on_ladder(day: date) -> bool:
    """Whether ``day`` resolves shutdown on the sleep ladder."""
    return day >= LADDER_FROM


def ladder_for(day: date) -> Mapping[str, Rung] | None:
    """The rungs in force on ``day``; ``None`` before the ladder."""
    if not on_ladder(day):
        return None
    return TUTOR_LADDER if day >= TUTOR_FROM else LADDER


def _rung(item: Earner, day: date) -> Rung | None:
    rungs = ladder_for(day)
    return None if rungs is None else rungs.get(item.name)


def shutdown_minutes_for(item: Earner, day: date) -> int:
    """What ``item``'s first unit pushes shutdown later by on ``day``.

    Its ladder rung from ``LADDER_FROM`` on; before that, or for an earner
    without a rung, its own ``shutdown_minutes``.
    """
    rung = _rung(item, day)
    return item.shutdown_minutes if rung is None else rung.first


def extra_shutdown_minutes_for(item: Earner, day: date) -> int:
    """What ``item``'s second unit earns on ``day`` (counted only)."""
    rung = _rung(item, day)
    return item.extra_shutdown_minutes if rung is None else rung.second


def shutdown_units_minutes(item: Earner, units: int, day: date) -> int:
    """What ``units`` (already capped by the caller) earn on ``day``."""
    if units <= 0:
        return 0
    rung = _rung(item, day)
    if rung is not None:
        return rung.minutes(units)
    return item.shutdown_minutes + (units - 1) * item.extra_shutdown_minutes


def shutdown_ceiling_for(day: date) -> int:
    """The latest shutdown ``day`` can earn, minutes after its midnight."""
    if on_ladder(day):
        return _DAY_MINUTES + WAKE_MINUTES - _SLEEP_MINUTES
    return SHUTDOWN_CEILING_MINUTES
