# Copyright (c) 2026 Krzysztof Rudnicki
"""The leisure budget: from ``LEISURE_FROM`` gaming time covers all leisure.

The daily "gaming" budget becomes a budget for every non-productive activity
on the PC (games, browsing, video, messaging), so a fully earned day grows
from 8 h to 10 h: the base rises 5 h -> 7 h and the cap 8 h -> 10 h. Earner
pay, penalties and the shutdown ladder are untouched, so a day still earns
exactly what it did; only the floor and the cap move, by the same 2 h.

Days before ``LEISURE_FROM`` keep ``GAMING_BASE_MINUTES`` and
``GAMING_CEILING_MINUTES``, byte-identical. ``resolve(..., leisure=True)``
prices any day as if ``LEISURE_FROM`` had already passed: the shadow budget
the enforcer reports during the shadow week, while it still enforces the old.
"""

from __future__ import annotations

from datetime import date
from typing import Final

from earned_time._policy import GAMING_BASE_MINUTES, GAMING_CEILING_MINUTES

# Parked far ahead: Phase 2 of the leisure rollout sets it to the day after
# kuhy confirms the shadow week, never a same-day cut (2026-09-26).
LEISURE_FROM: Final = date(2027, 1, 1)
# From ``LEISURE_FROM``: 7 h base, 10 h cap (+2 h each).
LEISURE_BASE_MINUTES: Final = 7 * 60
LEISURE_CEILING_MINUTES: Final = 10 * 60


def leisure_day(day: date, *, leisure: bool = False) -> date:
    """The day the gaming base and cap are priced on.

    ``day`` itself, unless ``leisure``: then no earlier than ``LEISURE_FROM``,
    so the shadow budget of an old day uses the leisure base and cap.
    """
    return max(day, LEISURE_FROM) if leisure else day


def gaming_base_minutes_for(day: date) -> int:
    """The gaming base before penalties: 7 h from ``LEISURE_FROM``, else 5 h."""
    return LEISURE_BASE_MINUTES if day >= LEISURE_FROM else GAMING_BASE_MINUTES


def gaming_ceiling_minutes_for(day: date) -> int:
    """The gaming cap: 10 h from ``LEISURE_FROM``, else 8 h."""
    return LEISURE_CEILING_MINUTES if day >= LEISURE_FROM else GAMING_CEILING_MINUTES
