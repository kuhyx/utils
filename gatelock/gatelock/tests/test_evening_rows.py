# Copyright (c) 2026 Krzysztof Rudnicki
"""Seeded state for the evening-chain tests: tmp ledgers signed with a tmp key.

Nothing here names a production path. ``seeded`` builds a ``Sources`` whose
home, key, free-day pool and sick-day pool all live under ``tmp_path``.
"""

from __future__ import annotations

from datetime import date, datetime, time
import json
from typing import TYPE_CHECKING

import earned_time
from earned_time import entry_signature
import freedays
import sickdays

from gatelock.evening_chain import Sources

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

KEY = b"evening-test-key"
DAY = date(2026, 11, 17)  # a Tuesday: the tutor's workday quota is 15 minutes
EVENING = datetime(2026, 11, 17, 20, 30).astimezone()
LATE = datetime(2026, 11, 17, 23, 0).astimezone()
LEDGERS = {
    "reading": earned_time.READING,
    "tutor": earned_time.TUTOR,
    "leetcode": earned_time.LEETCODE,
}


def stamp(hour: int = 19) -> float:
    """A unix time on DAY, local."""
    return datetime.combine(DAY, time(hour)).astimezone().timestamp()


def _signed(row: Mapping[str, object]) -> dict[str, object]:
    return {**row, "hmac": entry_signature(row, KEY)}


def reading_row() -> dict[str, object]:
    """A reading credit that earned the bonus today."""
    detail = {"bonus": "1", "ended_at": stamp()}
    return _signed({"kind": "credit", "entry_id": "r1", "detail": detail})


def leetcode_row() -> dict[str, object]:
    """The charge LeetCode writes once today's price is covered by solves."""
    detail = {"source": "leetcode"}
    row = {"kind": "charge", "entry_id": "l1", "day": DAY.isoformat(), "detail": detail}
    return _signed(row)


def tutor_row(minutes: int) -> dict[str, object]:
    """``minutes`` of tutoring ending today."""
    detail = {"minutes": minutes, "ended_at": stamp()}
    row = {"kind": "credit", "entry_id": f"s-m{minutes}", "detail": detail}
    return _signed({**row, "day": DAY.isoformat()})


def write_ledger(sources: Sources, rung: str, rows: list[dict[str, object]]) -> Path:
    """Write ``rows`` as ``rung``'s ledger under the tmp home."""
    path = sources.home / str(LEDGERS[rung].ledger)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"entries": rows}), encoding="utf-8")
    return path


def seeded(tmp_path: Path) -> Sources:
    """Empty sources: key present, no ledgers, no free or sick day."""
    key = tmp_path / "hmac.key"
    key.write_bytes(KEY)
    return Sources(
        home=tmp_path / "home",
        key_file=key,
        free_log=tmp_path / "free" / "free_days.json",
        sick_log=tmp_path / "sick" / "sick_days.json",
    )


def pay_all(sources: Sources) -> None:
    """Every rung paid today."""
    write_ledger(sources, "reading", [reading_row()])
    write_ledger(sources, "tutor", [tutor_row(15)])
    write_ledger(sources, "leetcode", [leetcode_row()])


def mark_free(sources: Sources) -> None:
    """Make DAY a free day in the tmp pool."""
    assert sources.free_log is not None
    paths = freedays.Paths.under(sources.free_log.parent)
    sources.free_log.parent.mkdir(parents=True, exist_ok=True)
    freedays.mark(DAY, paths=paths, now=DAY)


def mark_sick(sources: Sources) -> None:
    """Make DAY a sick day in the tmp pool."""
    assert sources.sick_log is not None
    paths = sickdays.Paths.under(sources.sick_log.parent)
    sources.sick_log.parent.mkdir(parents=True, exist_ok=True)
    sickdays.add_sick_day(DAY, paths=paths, is_free=lambda _day: False, now=DAY)
