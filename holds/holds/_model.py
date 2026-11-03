# Copyright (c) 2026 Krzysztof Rudnicki
"""The ``Hold`` record and its JSON row form (local, naive timestamps)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


class HoldsError(Exception):
    """A hold was refused by the ratchet rules, or the file cannot be trusted."""


def naive(moment: datetime) -> datetime:
    """Return ``moment`` as local wall-clock time without a tzinfo."""
    if moment.tzinfo is not None:
        return moment.astimezone().replace(tzinfo=None)
    return moment


@dataclass(frozen=True)
class Hold:
    """One declared window during which every gate stands down."""

    id: str
    start: datetime
    end: datetime
    reason: str
    created: datetime

    def contains(self, now: datetime) -> bool:
        """Half-open: active from ``start`` up to, not including, ``end``."""
        return self.start <= now < self.end

    def to_row(self) -> dict[str, str]:
        """Serialise as the contract row (start/end are whole minutes)."""
        return {
            "id": self.id,
            "start": self.start.isoformat(timespec="minutes"),
            "end": self.end.isoformat(timespec="minutes"),
            "reason": self.reason,
            "created": self.created.isoformat(timespec="seconds"),
        }

    @classmethod
    def from_row(cls, row: dict[str, str]) -> Hold:
        """Parse a row; raises KeyError/TypeError/ValueError when malformed."""
        return cls(
            id=str(row["id"]),
            start=naive(datetime.fromisoformat(row["start"])),
            end=naive(datetime.fromisoformat(row["end"])),
            reason=str(row["reason"]),
            created=naive(datetime.fromisoformat(row["created"])),
        )
