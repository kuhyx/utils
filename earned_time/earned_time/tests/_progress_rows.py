# Copyright (c) 2026 Krzysztof Rudnicki
"""Signed ``progress`` rows and ledger files for the partial-pay tests."""

from __future__ import annotations

from datetime import date
import json
from typing import TYPE_CHECKING

from earned_time.tests._maturity_rows import signed

if TYPE_CHECKING:
    from pathlib import Path

    from earned_time import Earner

# A day on the unified ladder, with the review top-up registered.
DAY = date(2026, 11, 24)


def progress(
    source: str = "leetcode",
    done: object = "1",
    target: object = "3",
    day: date = DAY,
    **detail: object,
) -> dict[str, object]:
    """One signed progress row, exactly as the gates write it."""
    fields: dict[str, object] = {
        "source": source,
        "for_day": day.isoformat(),
        "done": done,
        "target": target,
        **detail,
    }
    return signed(
        {
            "kind": "progress",
            "entry_id": f"progress:{day.isoformat()}:{done}:{target}",
            "day": day.isoformat(),
            "amount": 0,
            "device": "pc",
            "created_at": f"{day.isoformat()}T12:00:00+00:00",
            "detail": fields,
        }
    )


def write(path: Path, rows: list[object]) -> Path:
    """A ledger file at ``path`` holding ``rows``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"entries": rows}), encoding="utf-8")
    return path


def home_ledger(home: Path, earner: Earner) -> Path:
    """Where a consumer finds ``earner``'s ledger under ``home``."""
    return home / str(earner.ledger)


def tampered(row: dict[str, object], **detail: object) -> dict[str, object]:
    """``row`` with its detail edited after signing (the old HMAC kept)."""
    old = row["detail"]
    assert isinstance(old, dict)
    return {**row, "detail": {**old, **detail}}


def bare(
    done: object = "1",
    target: object = "3",
    source: str = "workout",
    day: date = DAY,
) -> dict[str, object]:
    """A signed progress row with no ``created_at`` and no ``device``.

    The workout ledger writes rows like this; the reader must accept them.
    """
    return signed(
        {
            "kind": "progress",
            "entry_id": f"progress:{day.isoformat()}:{done}:{target}",
            "day": day.isoformat(),
            "amount": 0,
            "detail": {
                "source": source,
                "for_day": day.isoformat(),
                "done": done,
                "target": target,
            },
        }
    )
