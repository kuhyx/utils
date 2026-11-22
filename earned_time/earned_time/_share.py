# Copyright (c) 2026 Krzysztof Rudnicki
"""Proportional pay (0.24.0): ``done`` of ``target`` units pays that share.

Equal slices, floored, nothing held back (kuhy, 2026-11-22: "50% of pages you
get 50% of bonus"). One piece of arithmetic for every earner that pays by
share: the focus earner's minutes and the gates' signed progress alike.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final

from earned_time._ladder import shutdown_minutes_for
from earned_time._resolution import Term

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import date

    from earned_time._policy import Earner
    from earned_time._progress import Progress

_logger: Final = logging.getLogger(__name__)


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


def share_term(item: Earner, units: int | None, day: date, share: Progress) -> Term:
    """``item``'s term on ``day`` when it is paid as a share of ``share``."""
    return Term(
        item,
        units,
        gaming_share(item, share),
        shutdown_share(item, share, day),
        share,
    )


def review_term(
    item: Earner,
    units: int | None,
    day: date,
    progress: Mapping[str, Progress] | None,
) -> Term:
    """The review's term from ``REVIEW_PROGRESS_FROM``: a credited review needs a row.

    Only a credited review (a yes) pays, and then ``bonus * done // target`` of
    the signed row, never more than the full bonus. A yes with no row pays 0:
    a row that fails verification is no row, so it pays 0 too (fail closed,
    logged). A no and ``None`` pay 0 whatever a row says, since the guard's
    accepted submission, not the row, is the evidence a review happened.
    """
    share = (progress or {}).get(item.name) if units else None
    if units and share is None:
        _logger.warning(
            "%s credited with no progress row on %s; it pays nothing",
            item.label,
            day,
        )
    if share is None:
        return Term(item, units, 0, 0)
    return share_term(item, units, day, share)
