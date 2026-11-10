# Copyright (c) 2026 Krzysztof Rudnicki
"""Interview milestones: generated from the project, judged from evidence.

Nothing here is stored or editable. ``due`` and the state are recomputed from
the project (kind, test_at, trips, weekend answers) and the append-only
evidence rows, so a milestone cannot be moved or ticked off by editing a row.

Failure modes (R8): an unanswered trip question reads as a trip (fail
closed); a check that could not run is ``unknown`` and counts as not done
(fail closed); an unreadable registry or evidence file arms no lock (fail
open, logged), matching focus-guard's "unreadable registry" rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import logging
from typing import TYPE_CHECKING, Any, Literal

from focus_project import _api, _interview, evidence
from focus_project._errors import RegistryError
from focus_project._kind import INTERVIEW

if TYPE_CHECKING:
    from collections.abc import Callable

    from focus_project._model import Project

_LOG = logging.getLogger(__name__)
State = Literal["pending", "done", "missed", "late_done", "unknown"]
PHONE_LEAD = timedelta(hours=12)
_RED = frozenset({"missed", "unknown"})


@dataclass(frozen=True)
class Milestone:
    """One generated obligation of an interview project."""

    id: str
    due: datetime
    state: State
    completed: bool

    @property
    def red(self) -> bool:
        """Past due and not done (also: the check could not run)."""
        return self.state in _RED

    def to_dict(self) -> dict[str, Any]:
        """The status() row: id, due ISO, state."""
        return {"id": self.id, "due": self.due.isoformat(), "state": self.state}


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute))


def _trip_due(trip_start: date, entered_ms: int) -> datetime:
    """Start - 12 h, or the moment it was entered if that left < 12 h."""
    nominal = _at(trip_start, 0) - PHONE_LEAD
    if entered_ms > 0:
        entered = evidence.from_ms(entered_ms)
        if nominal - entered < PHONE_LEAD:
            return entered
    return nominal


def _is_trip(
    *,
    answered: bool | None,
    answer_ms: int | None,
    ask_due: datetime,
    phone_due: datetime,
    now: datetime,
) -> bool:
    """Whether the weekend counts as a trip (fail closed).

    Unanswered once the question is due = a trip. A no-trip answer given
    only after the phone prep was already due cannot erase that overdue
    milestone: the answer row's own timestamp decides, not a stored flag.
    """
    if answered is None:
        return now >= ask_due
    if answered:
        return True
    return answer_ms is not None and answer_ms >= evidence.to_ms(phone_due)


def plan(
    project: Project, test_day: date, now: datetime, rows: list[evidence.Evidence]
) -> dict[str, datetime]:
    """Milestone id -> due; ``project`` must be a validated interview."""
    dues = {
        "rules": _at(project.start, 23, 59),
        "mock": _at(test_day - timedelta(days=2), 23, 59),
        "slot": _at(test_day - timedelta(days=1), 12),
    }
    answers = dict(project.weekend_answers)
    for sat in _interview.saturdays(project):
        ask_due = _at(sat - timedelta(days=2), 23, 59)
        phone_due = _at(sat, 0) - PHONE_LEAD
        dues[f"trip_ask:{sat}"] = ask_due
        covered = any(t.covers(sat) for t in project.trips)
        row = evidence.first(rows, f"trip_ask:{sat}", "answer")
        answer_ms = None if row is None else row.ms
        if not covered and _is_trip(
            answered=answers.get(sat),
            answer_ms=answer_ms,
            ask_due=ask_due,
            phone_due=phone_due,
            now=now,
        ):
            dues[f"phone:{sat}"] = phone_due
    for trip_row in project.trips:
        dues[f"phone:{trip_row.start}"] = _trip_due(trip_row.start, trip_row.entered_ms)
    return dues


def _when(row: evidence.Evidence | None) -> datetime | None:
    return None if row is None else row.at


Rows = list[evidence.Evidence]
Completion = tuple[datetime | None, bool]


def _by_evidence(kind: str) -> Callable[[str, Rows, Project], Completion]:
    """Done at the first evidence row of ``kind`` (rules file, mock score)."""

    def judge(mid: str, rows: Rows, _project: Project) -> Completion:
        return _when(evidence.first(rows, mid, kind)), False

    return judge


def _trip_ask(mid: str, rows: Rows, project: Project) -> Completion:
    """Done at the answer row; an answer with no row was given at creation."""
    if date.fromisoformat(mid.partition(":")[2]) not in dict(project.weekend_answers):
        return None, False
    return _when(evidence.first(rows, mid, "answer")) or evidence.from_ms(0), False


def _slot(mid: str, rows: Rows, _project: Project) -> Completion:
    """Done once the latest slot entry has a confirm tap at or after it."""
    slot = evidence.last(rows, mid, "slot")
    if slot is None:
        return None, False
    confirm = evidence.first(rows, mid, "slot_confirm", since_ms=slot.ms)
    return (None if confirm is None else max(slot.at, confirm.at)), False


def _phone(mid: str, rows: Rows, _project: Project) -> Completion:
    """Done when the offline tap and a passing auto check both exist.

    A tap with no verdict at all (or a dark source) is ``unknown``.
    """
    tap = evidence.first(rows, mid, "tap")
    passed, latest, _ = evidence.check_summary(rows, mid)
    if tap is not None and passed is not None:
        return max(tap.at, evidence.from_ms(passed)), False
    return None, tap is not None and latest is None


_JUDGES = {
    "rules": _by_evidence("file"),
    "mock": _by_evidence("score"),
    "trip_ask": _trip_ask,
    "slot": _slot,
    "phone": _phone,
}


def _judge(
    mid: str, due: datetime, rows: Rows, project: Project, now: datetime
) -> Milestone:
    done_at, unknown = _JUDGES[mid.partition(":")[0]](mid, rows, project)
    if done_at is not None:
        state: State = "done" if done_at <= due else "late_done"
        return Milestone(mid, due, state, completed=True)
    if now < due:
        return Milestone(mid, due, "pending", completed=False)
    return Milestone(mid, due, "unknown" if unknown else "missed", completed=False)


def milestones(project: Project, now: datetime) -> list[Milestone]:
    """The project's milestones at ``now`` (naive local), earliest due first.

    Empty for a focus project. May raise OSError reading the evidence file.
    """
    if project.kind != INTERVIEW or project.test_at is None:
        return []
    rows = evidence.read(project.id)
    dues = plan(project, project.test_at.date(), now, rows)
    found = [_judge(mid, due, rows, project, now) for mid, due in dues.items()]
    return sorted(found, key=lambda m: (m.due, m.id))


def owed_lock(now: datetime) -> Milestone | None:
    """The earliest overdue, uncompleted milestone that locks, or None.

    Locks (missed or unknown) from the moment it is due, every day of the
    project except the test day itself, where nothing locks. It does not
    consult sickdays/freedays: focus-guard's ``_off(today)`` precondition
    already stands the lock down on those days, so wire this after it.
    Unreadable state arms nothing (fail open, logged).
    """
    try:
        project = _api.active(now.date())
        if project is None or project.test_at is None:
            return None
        if now.date() >= project.test_at.date():
            return None
        owed = [m for m in milestones(project, now) if not m.completed and now >= m.due]
    except (RegistryError, OSError) as exc:
        _LOG.warning("interview state unreadable, no milestone lock: %s", exc)
        return None
    return owed[0] if owed else None
