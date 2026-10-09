# Copyright (c) 2026 Krzysztof Rudnicki
"""Signed ledger rows and files for the maturity tests."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
import json
from typing import TYPE_CHECKING

from earned_time import entry_signature

if TYPE_CHECKING:
    from pathlib import Path

KEY = b"test-key"
TODAY = date(2026, 10, 9)


def at(day: date, hour: int = 12) -> str:
    """``day`` at ``hour`` local, as a unix-stamp string."""
    return str(datetime.combine(day, time(hour)).astimezone().timestamp())


def signed(row: dict[str, object]) -> dict[str, object]:
    """``row`` with its HMAC under :data:`KEY`."""
    return {**row, "hmac": entry_signature(row, KEY)}


def solve(day: date, entry: str | None = None, **extra: object) -> dict[str, object]:
    """A signed LeetCode solve credited on ``day``."""
    row: dict[str, object] = {
        "kind": "credit",
        "entry_id": entry or f"ac:{day}",
        "day": day.isoformat(),
        "amount": 1,
        "detail": {"source": "leetcode", "submitted_at": at(day)},
        **extra,
    }
    return signed(row)


def ledger_file(tmp_path: Path, rows: list[object]) -> Path:
    """A ledger file holding ``rows``."""
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps({"entries": rows}), encoding="utf-8")
    return path


def grant(
    *,
    entry: str = "bonus:session:a",
    amount: object = 0,
    grant_of: object = "session:a",
    source: str | None = None,
) -> dict[str, object]:
    """A book-guard bonus re-evaluation row: signed, ``amount`` 0, ``grant_of``."""
    detail: dict[str, object] = {"bonus": "1", "ended_at": at(TODAY)}
    detail["grant_of"] = grant_of
    if source is not None:
        detail["source"] = source
    row = {"kind": "credit", "entry_id": entry, "amount": amount, "detail": detail}
    return signed(row)


def days(first: date, count: int) -> list[object]:
    """One solve on each of ``count`` days from ``first``."""
    return [solve(first + timedelta(days=i)) for i in range(count)]
