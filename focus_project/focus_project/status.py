# Copyright (c) 2026 Krzysztof Rudnicki
"""status(day): the dict i3bar, daily-limits and the GUIs render."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from focus_project import _api, _milestones, carry, evidence

if TYPE_CHECKING:
    from datetime import date

    from focus_project._model import Project

_LOG = logging.getLogger(__name__)


def _milestone_block(project: Project) -> tuple[list[dict[str, Any]], bool]:
    """Milestone rows and whether any is red; unreadable evidence shows none.

    Display path, so it fails open (logged): the lock path, ``owed_lock``,
    has its own handling.
    """
    now = evidence.clock_now()
    try:
        items = _milestones.milestones(project, now)
    except OSError as exc:
        _LOG.warning("interview evidence unreadable, no milestones shown: %s", exc)
        return [], False
    return [m.to_dict() for m in items], any(m.red for m in items)


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
            "milestones": [],
            "missed": False,
        }
    daily = project.daily_on(day)
    bank = carry.balance(day)
    rows, missed = _milestone_block(project)
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
        # Interview projects: [{id, due ISO, state}] and whether any is red.
        "milestones": rows,
        "missed": missed,
    }
