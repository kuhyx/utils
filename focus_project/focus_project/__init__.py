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
    end_project,
    list_projects,
    stands_down,
)
from focus_project._errors import RegistryError
from focus_project._model import Limits, Project
from focus_project._update import Update, apply_update, update_project
from focus_project.activity import record_activity
from focus_project.minutes import minutes_for
from focus_project.status import status

__all__ = [
    "Limits",
    "Project",
    "RegistryError",
    "Update",
    "active",
    "apply_update",
    "create_project",
    "end_project",
    "list_projects",
    "minutes_for",
    "record_activity",
    "stands_down",
    "status",
    "update_project",
]
