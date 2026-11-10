# Copyright (c) 2026 Krzysztof Rudnicki
"""Time-boxed focus projects that replace chosen gates.

A gate's whole integration::

    import focus_project

    if focus_project.stands_down("leetcode", today):
        ...  # this gate is off for the active project: no charge, debt or lock

``stands_down`` never raises: an unreadable registry reads as "not standing
down", so the failure mode is "the normal rules apply".
"""

from __future__ import annotations

from focus_project._api import (
    active,
    create_project,
    daily_floor,
    end_project,
    list_projects,
    stands_down,
)
from focus_project._errors import RegistryError
from focus_project._milestones import Milestone, milestones, owed_lock
from focus_project._model import Limits, Project
from focus_project._mutate import add_trip, answer_weekend, record_evidence
from focus_project._trips import Trip
from focus_project._update import Update, apply_update, update_project
from focus_project.activity import record_activity
from focus_project.checks import register_source, run_checks
from focus_project.evidence import Evidence
from focus_project.minutes import minutes_for, unbacked_minutes_for
from focus_project.sources.activity import BACKING_FROM
from focus_project.status import status

__all__ = [
    "BACKING_FROM",
    "Evidence",
    "Limits",
    "Milestone",
    "Project",
    "RegistryError",
    "Trip",
    "Update",
    "active",
    "add_trip",
    "answer_weekend",
    "apply_update",
    "create_project",
    "daily_floor",
    "end_project",
    "list_projects",
    "milestones",
    "minutes_for",
    "owed_lock",
    "record_activity",
    "record_evidence",
    "register_source",
    "run_checks",
    "stands_down",
    "status",
    "unbacked_minutes_for",
    "update_project",
]
