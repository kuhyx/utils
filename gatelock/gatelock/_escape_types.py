"""The policy, history and draft types the escape hatch works with.

Split from :mod:`gatelock._escape`, which keeps the tracker. Data and two date
helpers, no I/O, so the shapes can be read without the persistence around them.

Re-exported from :mod:`gatelock._escape`, so existing imports keep working.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Any

_logger = logging.getLogger(__name__)

_DATE_FORMAT = "%Y-%m-%d"


@dataclass(frozen=True)
class EscapePolicy:
    """How hard one app's escape hatch is to use.

    Defaults mirror screen-locker's sick mode, which is the proven shape.

    Attributes:
        name: Short identifier used in logs and the summary line.
        label: Human wording for one use, e.g. "sick day".
        budget_per_7_days: Uses allowed in a rolling week.
        budget_per_30_days: Uses allowed in a rolling month.
        budget_per_90_days: Uses allowed in a rolling quarter.
        lockout_seconds: Base wait before the hatch actually opens.
        lockout_multiplier_per_recent: Wait multiplier per use in 30 days.
        justification_min_chars: Minimum length of the written reason.
        history_review_count: How many past reasons to show back to the user.
    """

    name: str
    label: str
    budget_per_7_days: int = 1
    budget_per_30_days: int = 3
    budget_per_90_days: int = 10
    lockout_seconds: int = 120
    lockout_multiplier_per_recent: int = 2
    justification_min_chars: int = 120
    history_review_count: int = 10


@dataclass
class EscapeHistory:
    """Persistent record of every use of one app's hatch."""

    used_days: list[str] = field(default_factory=list)
    justifications: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class EscapeDraft:
    """A proposed use of the hatch, before validation."""

    reason: str
    onset: str
    severity: int
    description: str


def _today_iso() -> str:
    """Return today's date as ``YYYY-MM-DD`` (UTC)."""
    return datetime.now(tz=timezone.utc).strftime(_DATE_FORMAT)


def _parse_iso(date_str: str) -> datetime | None:
    """Parse ``YYYY-MM-DD`` into a UTC datetime, or None if unparsable.

    An unparsable entry is *ignored* rather than fatal, but logged loudly:
    silently counting it as zero would quietly widen the budget.
    """
    try:
        return datetime.strptime(date_str, _DATE_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        _logger.warning(
            "escape history holds an unparsable date %r (%s) -- that entry is "
            "IGNORED when counting against the budget",
            date_str,
            exc,
        )
        return None
