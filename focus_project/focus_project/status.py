# Copyright (c) 2026 Krzysztof Rudnicki
"""status(day): the dict i3bar, daily-limits and the GUIs render."""

from __future__ import annotations

from datetime import date  # noqa: TC003
from typing import Any

from focus_project import _api, carry


def status(day: date) -> dict[str, Any]:
    """Progress of the project active on ``day``; ``project`` is None if none.

    ``minutes`` is what was really worked plus what the day took from the
    bank, so it may exceed ``daily_minutes`` (121/120); ``counted_minutes``
    is the capped figure that pays.
    """
    project = _api.active(day)
    if project is None:
        return {
            "project": None,
            "name": None,
            "minutes": 0,
            "own_minutes": 0,
            "counted_minutes": 0,
            "carried_in": 0,
            "carry_out": 0,
            "daily_minutes": None,
            "unlock_minutes": None,
            "ends": None,
            "replaces": [],
        }
    daily = project.daily_on(day)
    bank = carry.balance(day)
    return {
        "project": project.id,
        "name": project.name,
        # Real minutes behind the day (own + banked in), never capped: the
        # number to show. Pay is ``counted_minutes``; earned_time caps it.
        "minutes": bank.own + bank.carried_in,
        "own_minutes": bank.own,
        "counted_minutes": bank.counted(daily),
        "carried_in": bank.carried_in,
        "carry_out": bank.carry_out,
        "daily_minutes": daily,
        "unlock_minutes": project.unlock_on(day),
        "ends": project.last_day.isoformat(),
        "replaces": list(project.replaces_on(day)),
    }
