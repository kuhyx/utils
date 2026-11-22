# Copyright (c) 2026 Krzysztof Rudnicki
"""Proportional pay (0.24.0): ``done`` of ``target`` units pays that share.

Equal slices, floored, nothing held back (kuhy, 2026-11-22: "50% of pages you
get 50% of bonus"). One piece of arithmetic for every earner that pays by
share: the focus earner's minutes and the gates' signed progress alike.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from earned_time._ladder import shutdown_minutes_for

if TYPE_CHECKING:
    from datetime import date

    from earned_time._policy import Earner
    from earned_time._progress import Progress


def share_minutes(full: int, done: int, target: int) -> int:
    """``full * done // target``, ``done`` clamped to ``[0, target]``.

    A ``target`` below 1 has no share to pay: ``0``, never a division error.
    """
    if target < 1:
        return 0
    return full * min(max(done, 0), target) // target


def gaming_share(item: Earner, progress: Progress) -> int:
    """The gaming minutes ``progress`` earns ``item``: a share of its first unit."""
    return share_minutes(item.gaming_for(1), progress.done, progress.target)


def shutdown_share(item: Earner, progress: Progress, day: date) -> int:
    """The shutdown minutes ``progress`` earns ``item`` on ``day``.

    A share of what :func:`~earned_time.shutdown_minutes_for` says a yes pays
    that day, so the ladder rung (not the pre-ladder number) is what is split.
    """
    return share_minutes(
        shutdown_minutes_for(item, day), progress.done, progress.target
    )
