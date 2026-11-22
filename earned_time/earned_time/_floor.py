# Copyright (c) 2026 Krzysztof Rudnicki
"""The floor's parts: what a penalty cuts, when it bites, the shutdown floor.

Split from :mod:`earned_time._resolve` (0.24.0) to keep both under the line
cap; :func:`earned_time.base_for` is still defined there.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from earned_time._focus import FocusEarner
from earned_time._ladder import on_ladder, shutdown_ceiling_for
from earned_time._maturity import confirmed_start, penalty_start
from earned_time._policy import SHUTDOWN_BASE_MINUTES

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import date

    from earned_time._policy import Earner


def gaming_cut(item: Earner) -> int:
    """What a penalty in force takes off the gaming base: all ``item`` can pay.

    A focus earner cuts what the gates it replaced paid; it pays more (0.21.0).
    """
    if isinstance(item, FocusEarner):
        return item.cut_gaming_minutes
    return item.max_gaming_minutes


def is_penalised(
    item: Earner, day: date, first_credits: Mapping[str, date | None] | None
) -> bool:
    """Whether ``item``'s cut is in force on ``day``.

    Without ``first_credits``: ``penalty_from`` alone, as in 0.5.0. With it:
    :func:`penalty_start` of the earner's first real credit (``None`` -- never
    paid out, or could not check -- is not penalised unless ``confirmed_on``
    is set: fail closed); an earner missing from it still waits for the day
    after its ``confirmed_on``.
    """
    if first_credits is None:
        return item.penalised_on(day)
    start = (
        penalty_start(item, first_credits[item.name])
        if item.name in first_credits
        else confirmed_start(item)
    )
    return start is not None and day >= start


def shutdown_floor(day: date, earners: tuple[Earner, ...], cut: list[Earner]) -> int:
    """Shutdown of a day that earned nothing; ``cut``: the penalties in force.

    On the ladder: the ceiling minus the most each earner can pay (all of a
    capped earner's units), so doing everything lands exactly on the ceiling
    -- but only a pure bonus (no ``penalty_from``) or an earner in ``cut``: a
    gate whose penalty has not started cannot lower the floor (0.6.1), nor can
    a top-up (0.23.0). Before it: the old base minus the penalties in force.
    """
    if on_ladder(day):
        rungs = (
            e for e in earners if not e.topup and (e.penalty_from is None or e in cut)
        )
        return shutdown_ceiling_for(day) - sum(
            e.shutdown_for(e.max_units or 1, day) for e in rungs
        )
    return SHUTDOWN_BASE_MINUTES - sum(e.shutdown_minutes for e in cut)
