# Copyright (c) 2026 Krzysztof Rudnicki
"""Which HMAC-verified ``credit`` rows count for a window, per gate.

Each ledger-backed :class:`~earned_time._policy.Earner` names one of these as
its ``match``. They see only rows that already passed the signature check.
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    Window = tuple[float, float]
    CreditMatch = Callable[[dict[str, object], Window], bool]

_logger: Final = logging.getLogger(__name__)


def _within(raw: object, window: Window) -> bool | None:
    """Whether a unix-seconds stamp falls in ``window``; ``None`` if unusable."""
    try:
        stamp = float(str(raw))
    except ValueError:
        return None
    start, end = window
    return start <= stamp <= end


def leetcode_match(row: dict[str, object], window: Window) -> bool:
    """A solve counts on the day LeetCode accepted it (``submitted_at``).

    ``day`` is the *harvesting* run's date and runs late, so it is only the
    fallback for a row without a usable stamp: it can miss a late solve but
    never invent one.
    """
    detail = row.get("detail")
    raw = detail.get("submitted_at") if isinstance(detail, dict) else None
    if raw is not None:
        landed = _within(raw, window)
        if landed is not None:
            return landed
        _logger.warning(
            "LeetCode credit %r has an unparsable submitted_at (%r); "
            "falling back to its day key",
            row.get("entry_id"),
            raw,
        )
    local = datetime.fromtimestamp(window[0], tz=UTC).astimezone()
    return row.get("day") == local.date().isoformat()


def reading_match(row: dict[str, object], window: Window) -> bool:
    """A reading credit counts if it earned the bonus and ended today."""
    detail = row.get("detail")
    if not isinstance(detail, dict) or detail.get("bonus") != "1":
        return False
    landed = _within(detail.get("ended_at"), window)
    if landed is None:
        _logger.warning("reading credit %r has no usable ended_at", row.get("entry_id"))
        return False
    return landed


def anki_match(row: dict[str, object], window: Window) -> bool:
    """An Anki credit counts on its Anki day (``detail.anki_day``).

    anki-guard writes one row per Anki day, keyed on the collection's own day
    boundary, so the day it names is the day it pays -- no stamp to parse.
    """
    detail = row.get("detail")
    local = datetime.fromtimestamp(window[0], tz=UTC).astimezone().date()
    return isinstance(detail, dict) and detail.get("anki_day") == local.isoformat()


def workout_match(row: dict[str, object], window: Window) -> bool:
    """A workout credit counts when it was completed in the window.

    screen-locker writes one row per credited unit. A ``rest_day`` row is a
    credit for the day it names (``day``), not for when it was written, and
    only if it was declared (``declared_at``) before that day began: a rest
    day declared on the day itself is a skipped workout, not a rest day.
    """
    detail = row.get("detail")
    if not isinstance(detail, dict):
        return False
    if detail.get("source") == "rest_day":
        local = datetime.fromtimestamp(window[0], tz=UTC).astimezone().date()
        if row.get("day") != local.isoformat():
            return False
        try:
            declared = float(str(detail.get("declared_at")))
        except ValueError:
            declared = None
        if declared is None or declared >= window[0]:
            _logger.warning(
                "rest-day credit %r was not declared before its day (declared_at "
                "%r); it does not count",
                row.get("entry_id"),
                detail.get("declared_at"),
            )
            return False
        return True
    landed = _within(detail.get("completed_at"), window)
    if landed is None:
        _logger.warning(
            "workout credit %r has no usable completed_at", row.get("entry_id")
        )
        return False
    return landed


def tutor_match(row: dict[str, object], window: Window) -> bool:
    """A tutor block counts on the day it ended (``detail.ended_at``).

    The Automation tutor writes one row per finished 15-minute block; a
    session that runs past midnight pays the day each block ended on.
    """
    detail = row.get("detail")
    raw = detail.get("ended_at") if isinstance(detail, dict) else None
    landed = _within(raw, window)
    if landed is None:
        _logger.warning("tutor credit %r has no usable ended_at", row.get("entry_id"))
        return False
    return landed


# The ``detail`` field each matcher decides on: the unix second the work
# happened, which :func:`earned_time._credits.credit_time` reports. A matcher
# without one (Anki's day key) falls back to the row's ``created_at``.
CREDIT_STAMPS: Final[Mapping[CreditMatch, str]] = MappingProxyType(
    {
        leetcode_match: "submitted_at",
        reading_match: "ended_at",
        workout_match: "completed_at",
        tutor_match: "ended_at",
    }
)
