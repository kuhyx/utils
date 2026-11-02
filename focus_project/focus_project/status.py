# Copyright (c) 2026 Krzysztof Rudnicki
"""status(day): the dict i3bar, daily-limits and the GUIs render."""

from __future__ import annotations

from datetime import date  # noqa: TC003
from typing import Any

from focus_project import _api, minutes


def status(day: date) -> dict[str, Any]:
    """Progress of the project active on ``day``; ``project`` is None if none."""
    project = _api.active(day)
    if project is None:
        return {
            "project": None,
            "name": None,
            "minutes": 0,
            "daily_minutes": None,
            "unlock_minutes": None,
            "ends": None,
            "replaces": [],
        }
    return {
        "project": project.id,
        "name": project.name,
        "minutes": minutes.minutes_for(day),
        "daily_minutes": project.daily_minutes,
        "unlock_minutes": project.unlock_minutes,
        "ends": project.last_day.isoformat(),
        "replaces": list(project.replaces),
    }
