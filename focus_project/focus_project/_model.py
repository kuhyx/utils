# Copyright (c) 2026 Krzysztof Rudnicki
"""The :class:`Project` value and the gate vocabulary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from focus_project._errors import RegistryError

GATES = frozenset({"leetcode", "reading", "tutor"})
_ALIASES = {"book": "reading"}


def normalize_gate(gate: str) -> str:
    """Map the book/reading synonyms onto one name; others pass through."""
    return _ALIASES.get(gate, gate)


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

    @property
    def last_day(self) -> date:
        """The last active day: the early-end day if set, else ``end``."""
        return self.ended_on if self.ended_on is not None else self.end

    def covers(self, day: date) -> bool:
        """Whether this project is active on ``day``."""
        return self.start <= day <= self.last_day

    def replaces_gate(self, gate: str) -> bool:
        """Whether this project switches ``gate`` off."""
        return normalize_gate(gate) in self.replaces

    def to_dict(self) -> dict[str, Any]:
        """The projects.json row."""
        return {
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
        }

    @classmethod
    def from_dict(cls, row: Any) -> Project:  # noqa: ANN401
        """Parse a registry row, or raise :class:`RegistryError`."""
        try:
            ended = row.get("ended_on")
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
            )
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            msg = f"bad project row {row!r}: {exc}"
            raise RegistryError(msg) from exc
