# Copyright (c) 2026 Krzysztof Rudnicki
"""Interview mutations: trips, weekend answers, evidence. Stricter only."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
import math
from typing import TYPE_CHECKING

from focus_project import _interview, _milestones, _store, evidence
from focus_project._kind import INTERVIEW
from focus_project._trips import Trip, add

if TYPE_CHECKING:
    from pathlib import Path

    from focus_project._model import Project

# Which evidence kinds each milestone family accepts from a caller.
# ``check`` and ``answer`` are internal: written by run_checks/answer_weekend.
_ACCEPTS = {
    "rules": {"file"},
    "mock": {"score"},
    "slot": {"slot", "slot_confirm"},
    "phone": {"tap"},
}
# tutor's worker reports phone readiness under the bare id "phone".
_PHONE_REPORT = "phone"


def local_now(now: datetime | None) -> datetime:
    """``now`` or the clock's local time."""
    return evidence.clock_now() if now is None else now


def find(existing: list[Project], project_id: str) -> tuple[int, Project]:
    """Index and interview project; KeyError unknown, ValueError focus kind."""
    for i, project in enumerate(existing):
        if project.id == project_id:
            if project.kind != INTERVIEW:
                msg = f"{project_id!r} is not an interview project (no milestones)"
                raise ValueError(msg)
            return i, project
    raise KeyError(project_id)


def add_trip(
    project_id: str, start: date, end: date, *, now: datetime | None = None
) -> Project:
    """Announce a trip; it may only grow (see :func:`focus_project._trips.add`)."""
    stamp = local_now(now)
    with _store.locked():
        existing = _store.read_all()
        i, project = find(existing, project_id)
        trips = add(project.trips, Trip(start, end, evidence.to_ms(stamp)))
        updated = replace(project, trips=trips)
        _interview.validate(updated)
        existing[i] = updated
        _store.write_all(existing)
    return updated


def answer_weekend(
    project_id: str, saturday: date, *, trip: bool, now: datetime | None = None
) -> Project:
    """Answer the trip question of a weekend; True never flips back to False."""
    stamp = local_now(now)
    with _store.locked():
        existing = _store.read_all()
        i, project = find(existing, project_id)
        if saturday not in _interview.saturdays(project):
            msg = f"{saturday} is not a weekend of {project_id!r} before its test day"
            raise ValueError(msg)
        answers = dict(project.weekend_answers)
        current = answers.get(saturday)
        if current is trip:
            return project
        if current is True:
            msg = "a trip answer may only get stricter: it stays True"
            raise ValueError(msg)
        if not trip and any(t.covers(saturday) for t in project.trips):
            msg = f"an announced trip covers {saturday}: it cannot be a no-trip weekend"
            raise ValueError(msg)
        updated = replace(
            project, weekend_answers=tuple(sorted({**answers, saturday: trip}.items()))
        )
        # Evidence first: a crash between the two leaves the question open
        # (fail closed), never an answer with no time.
        evidence.append(project_id, f"trip_ask:{saturday}", "answer", trip, stamp)
        existing[i] = updated
        _store.write_all(existing)
    return updated


def _number(value: object) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not math.isfinite(value)
        or value < 0
    ):
        msg = "a score must be a finite, non-negative number"
        raise ValueError(msg)
    return value


def _count(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        msg = f"{label} must be a non-negative integer"
        raise ValueError(msg)
    return value


def _clean(
    project_id: str, kind: str, value: object, file: Path | None, stamp: datetime
) -> object:
    """The value to store for ``kind``; ValueError if it is not acceptable."""
    if kind == "file":
        if file is None or not file.is_file() or not file.stat().st_size:
            msg = "a non-empty file is required"
            raise ValueError(msg)
        return evidence.store_file(project_id, file, stamp)
    if kind == "score":
        return _number(value)
    if kind == "slot":
        moment = datetime.fromisoformat(str(value)) if isinstance(value, str) else None
        if moment is None or moment.tzinfo is not None:
            msg = "slot must be a naive local ISO datetime"
            raise ValueError(msg)
        return moment.isoformat()
    if kind == "phone_check":
        if not isinstance(value, dict) or not isinstance(value.get("plan"), bool):
            msg = "phone_check needs {plan: bool, due: int, seen_ms: int}"
            raise ValueError(msg)
        return {
            "plan": value["plan"],
            "due": _count(value.get("due"), "due"),
            "seen_ms": _count(value.get("seen_ms"), "seen_ms"),
        }
    if kind == "slot_confirm" and value not in {True, None}:
        msg = "slot_confirm is a tap: value True"
        raise ValueError(msg)
    return True  # tap, slot_confirm


def record_evidence(  # noqa: PLR0913
    project_id: str,
    milestone: str,
    kind: str,
    value: object = None,
    *,
    file: Path | None = None,
    now: datetime | None = None,
) -> evidence.Evidence:
    """Append evidence for a milestone; ValueError if it does not fit.

    Kinds: ``file`` (rules, copied from ``file``), ``tap`` (phone:*),
    ``score`` (mock), ``slot`` (ISO datetime) and ``slot_confirm`` (slot),
    ``phone_check`` ({plan, due, seen_ms}, milestone "phone", from tutor).
    There is no way to delete a row.
    """
    stamp = local_now(now)
    _, project = find(_store.read_all(), project_id)
    if milestone == _PHONE_REPORT:
        accepted = {"phone_check"}
    else:
        known = {m.id for m in _milestones.milestones(project, stamp)}
        accepted = _ACCEPTS.get(milestone.partition(":")[0], set())
        if milestone not in known:
            msg = f"{milestone!r} is not a milestone of {project_id!r}"
            raise ValueError(msg)
    if kind not in accepted:
        msg = f"{milestone!r} takes evidence kinds {sorted(accepted)}, not {kind!r}"
        raise ValueError(msg)
    return evidence.append(
        project_id, milestone, kind, _clean(project_id, kind, value, file, stamp), stamp
    )
