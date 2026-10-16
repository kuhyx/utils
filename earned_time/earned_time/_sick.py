# Copyright (c) 2026 Krzysztof Rudnicki
"""The sick-day shutdown floor (0.11.0).

On a sick day shutdown is never earlier than 20:00: the resolved shutdown is
``max(SICK_SHUTDOWN_FLOOR_MINUTES, the normal ladder result)``, still capped
at the day's ceiling. It is applied to the *final* sum, never to the base --
raising the base would stack every earner's minutes on top of 20:00.

Only shutdown moves. Gaming time, the registry, waivers and penalties are
untouched, and every earner still earns on a sick day.

Whether a day is sick is the consumer's answer (the ``sickdays`` pool):
this package is stdlib-only and never imports it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from earned_time._ladder import shutdown_ceiling_for

if TYPE_CHECKING:
    from datetime import date

# 20:00, minutes after local midnight.
SICK_SHUTDOWN_FLOOR_MINUTES: Final = 20 * 60


def sick_shutdown_minutes(minutes: int, day: date) -> int:
    """``minutes`` (a resolved shutdown) with the sick-day floor applied.

    Args:
        minutes: The normal resolved shutdown, minutes after midnight.
        day: The day, which picks the ceiling.

    Returns:
        ``min(ceiling, max(SICK_SHUTDOWN_FLOOR_MINUTES, minutes))``.
    """
    return min(shutdown_ceiling_for(day), max(SICK_SHUTDOWN_FLOOR_MINUTES, minutes))
