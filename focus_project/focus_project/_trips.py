# Copyright (c) 2026 Krzysztof Rudnicki
"""Trips: days away from the PC. They can only grow (ratchet)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from typing import Any


@dataclass(frozen=True)
class Trip:
    """An inclusive away range; ``entered_ms`` is when it was announced."""

    start: date
    end: date
    entered_ms: int = 0

    def covers(self, day: date) -> bool:
        """Whether ``day`` is inside the trip."""
        return self.start <= day <= self.end

    def to_dict(self) -> dict[str, Any]:
        """The projects.json row."""
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "entered_ms": self.entered_ms,
        }

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> Trip:
        """Parse a trip row (errors surface as RegistryError upstream)."""
        return cls(
            start=date.fromisoformat(row["start"]),
            end=date.fromisoformat(row["end"]),
            entered_ms=int(row.get("entered_ms", 0)),
        )


def add(trips: tuple[Trip, ...], new: Trip) -> tuple[Trip, ...]:
    """``trips`` plus ``new``; ValueError if that would loosen an old trip.

    A new range touching an old trip must cover it: it replaces the old one
    (keeping its entry time when the start did not move earlier). Anything
    that starts later or ends earlier than what is on file is refused.
    """
    kept: list[Trip] = []
    for old in trips:
        if old.start > new.end or new.start > old.end:
            kept.append(old)
        elif new.start <= old.start and new.end >= old.end:
            if new.start == old.start:
                new = replace(new, entered_ms=old.entered_ms)
        else:
            msg = (
                f"a trip may only get stricter: pass a range that covers "
                f"{old.start}..{old.end}"
            )
            raise ValueError(msg)
    return tuple(sorted([*kept, new], key=lambda t: t.start))
