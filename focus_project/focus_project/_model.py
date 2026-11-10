# Copyright (c) 2026 Krzysztof Rudnicki
"""The :class:`Project` value and the gate vocabulary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from focus_project._errors import RegistryError
from focus_project._kind import FOCUS, INTERVIEW, interview_minutes
from focus_project._trips import Trip

GATES = frozenset({"leetcode", "reading", "tutor"})
_ALIASES = {"book": "reading"}


def normalize_gate(gate: str) -> str:
    """Map the book/reading synonyms onto one name; others pass through."""
    return _ALIASES.get(gate, gate)


def _answers(raw: dict[str, Any] | None) -> tuple[tuple[date, bool], ...]:
    """Parse the saturday -> bool map; a non-bool answer is a bad row."""
    pairs = []
    for key, value in (raw or {}).items():
        if not isinstance(value, bool):
            msg = f"weekend answer for {key} is not true/false"
            raise TypeError(msg)
        pairs.append((date.fromisoformat(key), value))
    return tuple(sorted(pairs))


@dataclass(frozen=True)
class Limits:
    """The minute targets that held up to and including ``until``."""

    until: date
    daily_minutes: int
    unlock_minutes: int
    # None = a row from before 0.7.0: the project's current gates apply.
    replaces: tuple[str, ...] | None = None

    def to_dict(self) -> dict[str, Any]:
        """The history row in projects.json."""
        row: dict[str, Any] = {
            "until": self.until.isoformat(),
            "daily_minutes": self.daily_minutes,
            "unlock_minutes": self.unlock_minutes,
        }
        if self.replaces is not None:
            row["replaces"] = list(self.replaces)
        return row

    @classmethod
    def from_dict(cls, row: Any) -> Limits:  # noqa: ANN401
        """Parse a history row (errors surface as RegistryError upstream)."""
        gates = row.get("replaces")
        return cls(
            until=date.fromisoformat(row["until"]),
            daily_minutes=int(row["daily_minutes"]),
            unlock_minutes=int(row["unlock_minutes"]),
            replaces=None if gates is None else tuple(gates),
        )


@dataclass(frozen=True)
class Project:
    """One time-boxed focus project; at most one is active per day."""

    id: str
    name: str
    start: date
    end: date
    replaces: tuple[str, ...]
    daily_minutes: int
    unlock_minutes: int
    subjects: tuple[str, ...] = ()
    site_patterns: tuple[str, ...] = ()
    ended_on: date | None = None
    created_ms: int = 0
    # Where the work happens (http/https); empty = the first site pattern.
    work_url: str = ""
    # Earlier targets, oldest first: an edit applies from its day, never back.
    history: tuple[Limits, ...] = ()
    # "focus" (every pre-interview row) or "interview"; the rest is interview-only.
    kind: str = FOCUS
    # Local naive datetime of the test; its date is the project's last day.
    test_at: datetime | None = None
    invite_url: str = ""
    trips: tuple[Trip, ...] = ()
    # Saturday -> True (trip that weekend) / False (no trip); sorted pairs.
    weekend_answers: tuple[tuple[date, bool], ...] = ()

    def _limits_on(self, day: date) -> Limits | None:
        return next((h for h in self.history if day <= h.until), None)

    def daily_on(self, day: date) -> int:
        """The daily target that held on ``day``."""
        if self.kind == INTERVIEW:
            return interview_minutes(day)
        past = self._limits_on(day)
        return self.daily_minutes if past is None else past.daily_minutes

    def unlock_on(self, day: date) -> int:
        """The unlock target that held on ``day`` (clamped for an interview)."""
        past = self._limits_on(day)
        held = self.unlock_minutes if past is None else past.unlock_minutes
        return min(held, interview_minutes(day)) if self.kind == INTERVIEW else held

    def replaces_on(self, day: date) -> tuple[str, ...]:
        """The gates this project switched off on ``day``."""
        past = self._limits_on(day)
        return self.replaces if past is None or past.replaces is None else past.replaces

    @property
    def last_day(self) -> date:
        """The last active day: the early-end day if set, else ``end``."""
        return self.ended_on if self.ended_on is not None else self.end

    def covers(self, day: date) -> bool:
        """Whether this project is active on ``day``."""
        return self.start <= day <= self.last_day

    def replaces_gate(self, gate: str, day: date) -> bool:
        """Whether this project switches ``gate`` off on ``day``."""
        return normalize_gate(gate) in self.replaces_on(day)

    def to_dict(self) -> dict[str, Any]:
        """The projects.json row."""
        row: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "replaces": list(self.replaces),
            "daily_minutes": self.daily_minutes,
            "unlock_minutes": self.unlock_minutes,
            "subjects": list(self.subjects),
            "site_patterns": list(self.site_patterns),
            "ended_on": self.ended_on.isoformat() if self.ended_on else None,
            "created_ms": self.created_ms,
            "work_url": self.work_url,
            "history": [h.to_dict() for h in self.history],
            "kind": self.kind,
        }
        if self.kind == INTERVIEW:
            row["test_at"] = self.test_at.isoformat() if self.test_at else None
            row["invite_url"] = self.invite_url
            row["trips"] = [t.to_dict() for t in self.trips]
            row["weekend_answers"] = {
                day.isoformat(): trip for day, trip in self.weekend_answers
            }
        return row

    @classmethod
    def from_dict(cls, row: Any) -> Project:  # noqa: ANN401
        """Parse a registry row, or raise :class:`RegistryError`."""
        try:
            ended = row.get("ended_on")
            test_at = row.get("test_at")
            return cls(
                id=str(row["id"]),
                name=str(row["name"]),
                start=date.fromisoformat(row["start"]),
                end=date.fromisoformat(row["end"]),
                replaces=tuple(row["replaces"]),
                daily_minutes=int(row["daily_minutes"]),
                unlock_minutes=int(row["unlock_minutes"]),
                subjects=tuple(row.get("subjects", ())),
                site_patterns=tuple(row.get("site_patterns", ())),
                ended_on=date.fromisoformat(ended) if ended else None,
                created_ms=int(row.get("created_ms", 0)),
                work_url=str(row.get("work_url") or ""),
                history=tuple(Limits.from_dict(h) for h in row.get("history", ())),
                kind=str(row.get("kind") or FOCUS),
                test_at=datetime.fromisoformat(test_at) if test_at else None,
                invite_url=str(row.get("invite_url") or ""),
                trips=tuple(Trip.from_dict(t) for t in row.get("trips", ())),
                weekend_answers=_answers(row.get("weekend_answers")),
            )
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            msg = f"bad project row {row!r}: {exc}"
            raise RegistryError(msg) from exc
