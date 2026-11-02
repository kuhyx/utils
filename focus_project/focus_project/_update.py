# Copyright (c) 2026 Krzysztof Rudnicki
"""update_project: edit a project with create's validation, never the past."""

from __future__ import annotations

from dataclasses import dataclass, replace
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
        "work_url",
    }
)
_TUPLES = ("subjects", "site_patterns")


def _apply(project: Project, changes: dict[str, Any], today: date) -> Update:
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
    return _schedule(project, replace(project, **fields), today)


def _held(project: Project, day: date) -> Limits:
    """What held on ``day``: both targets and the replaced gates."""
    return Limits(
        day,
        project.daily_on(day),
        project.unlock_on(day),
        project.replaces_on(day),
    )


def _reduces(held: Limits, new: Project) -> bool:
    """Whether ``new`` asks less than ``held``: lower target or a gate more."""
    return (
        new.daily_minutes < held.daily_minutes
        or new.unlock_minutes < held.unlock_minutes
        or not set(new.replaces) <= set(held.replaces or ())
    )


def _schedule(old: Project, new: Project, today: date) -> Update:
    """Date the edit: a reduction of a started project waits for tomorrow.

    A raise (or a project that has not started) applies from ``today``; the
    days before keep what held. Anything that lowers a target or switches a
    gate off defers the whole edit one day, so no edit can undo a lock or
    cheapen the pay of a day already running.
    """
    if (old.daily_minutes, old.unlock_minutes, old.replaces) == (
        new.daily_minutes,
        new.unlock_minutes,
        new.replaces,
    ):
        return Update(new, today)
    deferred = today >= old.start and _reduces(_held(old, today), new)
    first = today + timedelta(days=1) if deferred else today
    last = first - timedelta(days=1)
    history = [h for h in old.history if h.until < first]
    held = _held(old, last)
    same = (held.daily_minutes, held.unlock_minutes, held.replaces) == (
        new.daily_minutes,
        new.unlock_minutes,
        new.replaces,
    )
    if last >= old.start and not same and not (history and history[-1].until == last):
        history.append(held)
    return Update(replace(new, history=tuple(history)), first)


@dataclass(frozen=True)
class Update:
    """An edited project and the first day its new targets and gates hold."""

    project: Project
    effective_from: date


def apply_update(
    project_id: str,
    *,
    today: date | None = None,
    **changes: Any,  # noqa: ANN401
) -> Update:
    """Edit ``project_id``; ValueError on bad input, overlap or a past edit.

    Editable: name, start, end, replaces, daily_minutes, unlock_minutes,
    subjects, site_patterns, work_url. A started project's start cannot move.
    An edit never lowers today's obligation (0.7.0): a lower daily or unlock
    target, or a gate added to ``replaces``, holds from tomorrow, the earlier
    days (today included) keep theirs. Raises, gates removed and edits to a
    project that has not started hold from ``today`` (default: now). The
    result says which: ``effective_from``. A mixed edit defers as a whole.
    KeyError for an unknown id.
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
            done = _apply(project, changes, today)
            edited = done.project
            _validate(edited)
            for other in existing:
                if other.id != project_id and (
                    edited.start <= other.last_day and other.start <= edited.last_day
                ):
                    msg = f"project overlaps {other.id!r}"
                    raise ValueError(msg)
            existing[i] = edited
            _store.write_all(existing)
            return done
    raise KeyError(project_id)


def update_project(
    project_id: str,
    *,
    today: date | None = None,
    **changes: Any,  # noqa: ANN401
) -> Project:
    """:func:`apply_update` returning just the project."""
    return apply_update(project_id, today=today, **changes).project
