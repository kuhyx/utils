# Copyright (c) 2026 Krzysztof Rudnicki
"""The tutor's weekday quota: how many minutes a full day's reward takes.

From ``TUTOR_QUOTA_FROM`` the tutor's full reward (all ``max_units``, 60 gaming
and 60 shutdown minutes) is paid for fewer minutes on most days: 15 on a
workday, 30 on Monday and Friday, 50 at the weekend. A day pays
``min(max_units, minutes * max_units // quota)`` -- scaled on the day's summed
minutes, never per row, so flooring loses at most one unit a day. Every quota
is at most ``max_units``, so the switch only ever raises what a day pays
(may land on its deploy day). Earlier days pay one unit per minute, as before.
"""

from __future__ import annotations

from datetime import date
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from earned_time._match import tutor_match

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from earned_time._policy import CreditMatch, Earner

# From this day (a Monday, kuhy's call on 2026-10-12) the weekday quota applies.
TUTOR_QUOTA_FROM: Final = date(2026, 10, 12)
# A literal copy of ``freedays.WORKDAYS`` (Tue/Wed/Thu, ``date.weekday()``):
# importing freedays pulls in crdt-sync, and earned_time is stdlib only. A
# drift test compares the two.
WORKDAYS: Final[frozenset[int]] = frozenset({1, 2, 3})
# The rest of the week, split: Monday/Friday and the weekend.
EDGE_DAYS: Final[frozenset[int]] = frozenset({0, 4})
WEEKEND: Final[frozenset[int]] = frozenset({5, 6})
# Minutes of tutoring the full reward takes, per weekday class.
TUTOR_QUOTA_MINUTES: Final[Mapping[frozenset[int], int]] = MappingProxyType(
    {WORKDAYS: 15, EDGE_DAYS: 30, WEEKEND: 50}
)


def tutor_quota_for(day: date) -> int | None:
    """Minutes the tutor's full reward takes on ``day``; ``None`` before it."""
    if day < TUTOR_QUOTA_FROM:
        return None
    weekday = day.weekday()
    return next(q for days, q in TUTOR_QUOTA_MINUTES.items() if weekday in days)


def tutor_day_units(earner: Earner, minutes: int, day: date) -> int:
    """Units ``minutes`` of tutoring pay on ``day``: scaled to its quota.

    Before ``TUTOR_QUOTA_FROM`` one unit per minute (``max_units`` still
    applied by :func:`~earned_time.resolve`); from it,
    ``min(max_units, minutes * max_units // quota)``.
    """
    quota = tutor_quota_for(day)
    if quota is None:
        return minutes
    most = earner.max_units or quota
    return earner.capped(minutes * most // quota)


# How a day's summed row units become the units it pays, per matcher; a
# matcher without an entry pays its sum unchanged.
DAY_UNITS: Final[Mapping[CreditMatch, Callable[[Earner, int, date], int]]] = (
    MappingProxyType({tutor_match: tutor_day_units})
)
