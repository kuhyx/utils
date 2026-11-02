# Copyright (c) 2026 Krzysztof Rudnicki
"""update_project: edit a project with create's validation, never the past."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from typing import Any

from focus_project import _store
from focus_project._api import _validate
from focus_project._model import Limits, Project, normalize_gate

_EDITABLE = frozenset(
    {
        "name",
        "start",
        "end",
        "replaces",
        "daily_minutes",
        "unlock_minutes",
        "subjects",
        "site_patterns",
    }
)
_TUPLES = ("subjects", "site_patterns")


def _apply(project: Project, changes: dict[str, Any], today: date) -> Project:
    """The edited project; ValueError for what an edit may not touch."""
    if project.ended_on is not None:
        msg = f"project {project.id!r} ended on {project.ended_on}"
        raise ValueError(msg)
    if project.last_day < today:
        msg = f"project {project.id!r} is over (ended {project.last_day})"
        raise ValueError(msg)
    fields = {k: v for k, v in changes.items() if k not in _TUPLES}
    if "replaces" in changes:
        fields["replaces"] = tuple(
            dict.fromkeys(map(normalize_gate, changes["replaces"]))
        )
    for key in _TUPLES:
        if key in changes:
            fields[key] = tuple(changes[key])
    new_start = changes.get("start", project.start)
    if new_start != project.start and today > min(project.start, new_start):
        msg = f"cannot move start of a started project ({project.start})"
        raise ValueError(msg)
    if "end" in changes and changes["end"] < today:
        msg = f"end {changes['end']} is in the past"
        raise ValueError(msg)
    edited = replace(project, **fields)
    return _keep_past_limits(project, edited, today)


def _keep_past_limits(old: Project, new: Project, today: date) -> Project:
    """Freeze the old targets for the days before ``today`` if they changed."""
    changed = (old.daily_minutes, old.unlock_minutes) != (
        new.daily_minutes,
        new.unlock_minutes,
    )
    cutoff = today - timedelta(days=1)
    if not changed or cutoff < old.start:
        return new
    if old.history and old.history[-1].until == cutoff:
        return new
    row = Limits(cutoff, old.daily_minutes, old.unlock_minutes)
    return replace(new, history=(*old.history, row))


def update_project(
    project_id: str,
    *,
    today: date | None = None,
    **changes: Any,  # noqa: ANN401
) -> Project:
    """Edit ``project_id``; ValueError on bad input, overlap or a past edit.

    Editable: name, start, end, replaces, daily_minutes, unlock_minutes,
    subjects, site_patterns. A started project's start cannot move; changed
    minute targets apply from ``today`` (default: now) on, earlier days keep
    theirs. KeyError for an unknown id.
    """
    unknown = sorted(set(changes) - _EDITABLE)
    if unknown:
        msg = f"cannot change {unknown}"
        raise ValueError(msg)
    today = today or date.today()  # noqa: DTZ011
    with _store.locked():
        existing = _store.read_all()
        for i, project in enumerate(existing):
            if project.id != project_id:
                continue
            edited = _apply(project, changes, today)
            _validate(edited)
            for other in existing:
                if other.id != project_id and (
                    edited.start <= other.last_day and other.start <= edited.last_day
                ):
                    msg = f"project overlaps {other.id!r}"
                    raise ValueError(msg)
            existing[i] = edited
            _store.write_all(existing)
            return edited
    raise KeyError(project_id)
