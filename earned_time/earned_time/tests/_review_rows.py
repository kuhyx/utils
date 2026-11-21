# Copyright (c) 2026 Krzysztof Rudnicki
"""A fake home with a coach review ledger and a LeetCode guard ledger."""

from __future__ import annotations

from datetime import date, datetime, time
import json
from typing import TYPE_CHECKING

from earned_time import GUARD_LEDGER, REVIEW, entry_signature
from earned_time.tests._maturity_rows import KEY, at

if TYPE_CHECKING:
    from pathlib import Path

# A day the review earner is registered on (REVIEW_FROM is 2026-11-23).
DAY = date(2026, 11, 24)
SLUG = "two-sum"


def sign(row: dict[str, object], key: bytes = KEY) -> dict[str, object]:
    """``row`` with its HMAC under ``key``."""
    return {**row, "hmac": entry_signature(row, key)}


def review(
    slug: str | None = SLUG, day: date = DAY, hour: int = 20, **detail: object
) -> dict[str, object]:
    """One signed coach row for a finished review, as the coach writes it."""
    fields: dict[str, object] = {
        "source": "leetcode-coach-review",
        "cause": "slow-solve",
        "finished_at": at(day, hour),
        **detail,
    }
    if slug is not None:
        fields["title_slug"] = slug
    return sign(
        {
            "entry_id": f"review:{slug}",
            "kind": "credit",
            "day": day.isoformat(),
            "created_at": datetime.combine(day, time(hour)).astimezone().isoformat(),
            "amount": 1,
            "device": "pc",
            "detail": fields,
        }
    )


def accepted(
    slug: str = SLUG,
    day: date = DAY,
    hour: int = 10,
    entry: str | None = None,
    **detail: object,
) -> dict[str, object]:
    """One signed LeetCode guard credit: an accepted submission of ``slug``."""
    return sign(
        {
            "entry_id": entry or f"ac:{slug}:{day}:{hour}",
            "kind": "credit",
            "day": day.isoformat(),
            "amount": 1,
            "detail": {
                "title_slug": slug,
                "source": "leetcode",
                "submitted_at": at(day, hour),
                **detail,
            },
        }
    )


def write(path: Path, rows: list[dict[str, object]]) -> Path:
    """Write ``rows`` as a ``{"version", "entries"}`` ledger at ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "entries": rows}), encoding="utf-8")
    return path


def home_with(
    home: Path,
    reviews: list[dict[str, object]],
    guard: list[dict[str, object]] | None,
) -> Path:
    """Lay both ledgers out under ``home``; returns the review ledger path.

    ``guard=None`` leaves the guard ledger missing.
    """
    if guard is not None:
        write(home / GUARD_LEDGER, guard)
    return write(home / str(REVIEW.ledger), reviews)


def evening(day: date = DAY) -> datetime:
    """``day`` at 22:00 local: every fixture row of the day lies before it."""
    return datetime.combine(day, time(22)).astimezone()
