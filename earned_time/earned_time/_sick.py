# Copyright (c) 2026 Krzysztof Rudnicki
"""The sick-day shutdown: 20:00 plus what the day earned, at gaming pay.

0.11.0 floored the final shutdown at 20:00 without stacking, so a sick day
that did LeetCode and reading still shut down at 20:10 (kuhy, 2026-10-17:
"+1 h from book and +1 h from LeetCode" was expected). Since 0.13.0 a sick
day shuts down at ``SICK_SHUTDOWN_FLOOR_MINUTES`` plus every term's *gaming*
minutes (shutdown follows the gaming bonus), capped at the day's ceiling.
Never below 0.11.0's ``max(20:00, earned)``: every earner's gaming pay is at
least its rung and the ladder floor is below 20:00, so it may land same-day.

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


def sick_shutdown_from(paid_minutes: int, day: date) -> int:
    """A sick day's shutdown: 20:00 plus ``paid_minutes``, capped.

    Args:
        paid_minutes: The day's terms at gaming pay (``sum(t.gaming_minutes)``).
        day: The day, which picks the ceiling.

    Returns:
        ``min(ceiling, SICK_SHUTDOWN_FLOOR_MINUTES + paid_minutes)``.
    """
    return min(shutdown_ceiling_for(day), SICK_SHUTDOWN_FLOOR_MINUTES + paid_minutes)
