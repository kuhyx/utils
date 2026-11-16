# Copyright (c) 2026 Krzysztof Rudnicki
"""The gaming stick is gone: from ``GAMING_UNLIMITED_FROM`` nothing limits gaming.

kuhy's decision (2026-11-16): the daily gaming budget is removed completely.
Only shutdown time is the carrot -- everything done still shuts down at 23:00,
the ladder, its floor and every rung are unchanged. A removed limit is
raise-only, so the date is the day the decision was taken and it lands the
same day.

Nothing is deleted: ``gaming_minutes``, ``GAMING_*`` and the leisure API keep
resolving numbers (history, the shadow budget), so a consumer still importing
them keeps working. A consumer that *applies* a gaming budget must ask
:func:`gaming_enforced` (or read ``Resolution.gaming_enforced``) first and, on
``False``, lift the limit instead of enforcing the number.
"""

from __future__ import annotations

from datetime import date
from typing import Final

# The first day without a gaming budget. A gaming day (06:00 start): a consumer
# billing before 06:00 passes the gaming day, not the calendar day.
GAMING_UNLIMITED_FROM: Final = date(2026, 11, 16)


def gaming_enforced(day: date) -> bool:
    """Is a gaming budget enforced on ``day``? ``False`` from the switch date.

    Args:
        day: The gaming day.

    Returns:
        ``day < GAMING_UNLIMITED_FROM``. Before it the budget is exactly what
        0.21.0 resolved; from it ``resolve(...).gaming_minutes`` is history,
        not a limit.
    """
    return day < GAMING_UNLIMITED_FROM
