# Copyright (c) 2026 Krzysztof Rudnicki
"""The registry API: active, stands_down, create/end/list."""

from __future__ import annotations

from dataclasses import replace
from datetime import date  # noqa: TC003
import logging
import re
import time

from focus_project import _clock, _store
from focus_project._errors import RegistryError
from focus_project._model import GATES, Project, normalize_gate

_LOG = logging.getLogger(__name__)
_ID = re.compile(r"[a-z0-9][a-z0-9-]*")


def list_projects() -> list[Project]:
    """Every project in the registry, in file order."""
    return _store.read_all()


def active(day: date) -> Project | None:
    """The project active on ``day``, or None. Raises on a corrupt registry."""
    hits = [p for p in _store.read_all() if p.covers(day)]
    if len(hits) > 1:
        msg = f"projects overlap on {day}: {[p.id for p in hits]}"
        raise RegistryError(msg)
    return hits[0] if hits else None


def stands_down(gate: str, day: date) -> bool:
    """True iff the active project replaces ``gate``; never raises.

    Fail-closed: an unreadable registry means the gate stays ON (logged),
    never that a gate is silently switched off.
    """
    try:
        project = active(day)
    except (RegistryError, OSError) as exc:
        _LOG.warning(
            "focus_project registry unreadable, gate %s stays on: %s", gate, exc
        )
        return False
    return project is not None and project.replaces_gate(gate)


def _validate(project: Project) -> None:
    if not _ID.fullmatch(project.id):
        msg = f"id {project.id!r} must be a lowercase slug"
        raise ValueError(msg)
    if not project.name.strip():
        msg = "name must not be blank"
        raise ValueError(msg)
    if project.end < project.start:
        msg = "end is before start"
        raise ValueError(msg)
    if not project.replaces or not set(project.replaces) <= GATES:
        msg = f"replaces must be a non-empty subset of gates {sorted(GATES)}"
        raise ValueError(msg)
    if project.daily_minutes <= 0:
        msg = "daily_minutes must be positive"
        raise ValueError(msg)
    if not 0 <= project.unlock_minutes <= project.daily_minutes:
        msg = "unlock_minutes must be within 0..daily_minutes"
        raise ValueError(msg)


def create_project(  # noqa: PLR0913
    project_id: str,
    *,
    name: str,
    start: date,
    end: date,
    replaces: list[str],
    daily_minutes: int,
    unlock_minutes: int,
    subjects: list[str] | None = None,
    site_patterns: list[str] | None = None,
) -> Project:
    """Add a project; ValueError on bad input, a duplicate id or an overlap."""
    project = Project(
        id=project_id,
        name=name,
        start=start,
        end=end,
        replaces=tuple(dict.fromkeys(normalize_gate(g) for g in replaces)),
        daily_minutes=daily_minutes,
        unlock_minutes=unlock_minutes,
        subjects=tuple(subjects or ()),
        site_patterns=tuple(site_patterns or ()),
        created_ms=time.time_ns() // 1_000_000,
    )
    _validate(project)
    with _store.locked():
        existing = _store.read_all()
        for other in existing:
            if other.id == project.id:
                msg = f"project {project.id!r} already exists"
                raise ValueError(msg)
            if project.start <= other.last_day and other.start <= project.last_day:
                msg = f"project overlaps {other.id!r} ({other.start}..{other.last_day})"
                raise ValueError(msg)
        _store.write_all([*existing, project])
    return project


def end_project(project_id: str, day: date) -> Project:
    """End early: ``day`` becomes the last active day (clamped to ``end``).

    ``day`` must be today or later: ending a past day would retroactively
    erase that day's shortfall (and the lock it causes).
    """
    with _store.locked():
        existing = _store.read_all()
        for i, project in enumerate(existing):
            if project.id != project_id:
                continue
            if project.ended_on is not None:
                msg = f"project {project_id!r} already ended on {project.ended_on}"
                raise ValueError(msg)
            if day < project.start:
                msg = f"cannot end {project_id!r} before its start {project.start}"
                raise ValueError(msg)
            if day < _clock.today():
                msg = f"cannot end {project_id!r} in the past ({day})"
                raise ValueError(msg)
            ended = replace(project, ended_on=min(day, project.end))
            existing[i] = ended
            _store.write_all(existing)
            return ended
    raise KeyError(project_id)
