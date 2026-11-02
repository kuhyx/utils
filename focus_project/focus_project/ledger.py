# Copyright (c) 2026 Krzysztof Rudnicki
"""The signed credit ledger the ``focus`` earner reads.

Row contract (earned_time's "tutor row contract"): ``detail.minutes`` is the
positive increment the row pays, ``entry_id`` is
``<project>-<YYYYMMDD>-m<n>`` with ``n`` the day's cumulative credited
minutes AFTER the row (so ids never overlap and a retry rewrites the same
id), ``day`` is the local date, ``detail.ended_at`` is when the last paid
minute ended and never passes the day's end. The only writer is the
harvester; every write is read back and verified.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
from pathlib import Path
import tempfile
import time
from typing import TYPE_CHECKING, Any, Final

import earned_time

from focus_project._paths import data_dir
from focus_project.sources import day_bounds

if TYPE_CHECKING:
    from datetime import date

    from focus_project._model import Project

CREDIT: Final = "credit"
KEY_ENV: Final = "FOCUS_PROJECT_KEY"
_REAL_KEY: Final = Path("/etc/workout-locker/hmac.key")
_LOG = logging.getLogger(__name__)


class LedgerError(Exception):
    """The ledger exists but is not a ledger: never silently emptied."""


def key_path() -> Path:
    """The signing key: ``$FOCUS_PROJECT_KEY`` or the shared root-owned key."""
    override = os.environ.get(KEY_ENV)
    return Path(override) if override else _REAL_KEY


def ledger_path() -> Path:
    """The ledger file inside the data dir."""
    return data_dir() / "ledger.json"


def read_key() -> bytes | None:
    """The signing key, or None if unreadable or empty (logged)."""
    try:
        return key_path().read_bytes().strip() or None
    except OSError as exc:
        _LOG.warning("signing key %s unreadable: %s", key_path(), exc)
        return None


def read_rows(path: Path) -> list[Any]:
    """The raw ``entries`` array; a missing file is empty.

    Raises:
        LedgerError: unreadable, not JSON, or no entries array.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as exc:
        msg = f"{path} is unreadable: {exc}"
        raise LedgerError(msg) from exc
    rows = raw.get("entries") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        msg = f"{path} has no entries array"
        raise LedgerError(msg)
    return rows


def _write_rows(path: Path, rows: list[Any]) -> None:
    """Atomically replace the ledger: readers see the old file or the new one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False
    ) as handle:
        json.dump({"version": 1, "entries": rows}, handle, indent=1)
        handle.flush()
        os.fsync(handle.fileno())
    Path(handle.name).replace(path)


def paid_minutes(rows: list[Any], key: bytes, project_id: str, day: date) -> int:
    """Minutes already paid for ``project_id`` on ``day`` by verified rows.

    A repeated ``entry_id`` pays once, at its smallest count.
    """
    by_id: dict[str, int] = {}
    for row in rows:
        if not (isinstance(row, dict) and row.get("kind") == CREDIT):
            continue
        detail = row.get("detail")
        if not isinstance(detail, dict):
            continue
        minutes = detail.get("minutes")
        if (
            row.get("day") != day.isoformat()
            or detail.get("project") != project_id
            or not isinstance(minutes, int)
            or isinstance(minutes, bool)
            or minutes < 1
            or not earned_time.verified(row, key)
        ):
            continue
        eid = str(row.get("entry_id"))
        by_id[eid] = min(by_id.get(eid, minutes), minutes)
    return sum(by_id.values())


def build_row(  # noqa: PLR0913
    project_id: str, day: date, total: int, minutes: int, key: bytes, *, now: float
) -> dict[str, Any]:
    """The signed row paying ``minutes`` that bring the day's total to ``total``."""
    ended = min(now, day_bounds(day)[1] - 1)
    row: dict[str, Any] = {
        "kind": CREDIT,
        "entry_id": f"{project_id}-{day:%Y%m%d}-m{total}",
        "day": day.isoformat(),
        "created_at": float(now),
        "detail": {
            "project": project_id,
            "minutes": int(minutes),
            "total": int(total),
            "ended_at": float(ended),
        },
    }
    row["hmac"] = str(earned_time.entry_signature(row, key))
    return row


def credit_to(
    project: Project, day: date, total: int, *, now: float | None = None
) -> int:
    """Pay the day up to ``total`` cumulative minutes; return minutes added.

    Idempotent: nothing is written when the ledger already pays ``total`` or
    more. Raises LedgerError (unreadable ledger, unreadable key, unverifiable
    write) so the harvester can fail loudly instead of crediting nothing quietly.
    """
    key = read_key()
    if key is None:
        msg = f"signing key {key_path()} unreadable"
        raise LedgerError(msg)
    path = ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        rows = read_rows(path)
        paid = paid_minutes(rows, key, project.id, day)
        if total <= paid:
            return 0
        row = build_row(
            project.id, day, total, total - paid, key, now=now or time.time()
        )
        if any(
            isinstance(r, dict) and r.get("entry_id") == row["entry_id"] for r in rows
        ):
            msg = f"entry_id {row['entry_id']} already present but unverified"
            raise LedgerError(msg)
        _write_rows(path, [*rows, row])
        stored = read_rows(path)
    if paid_minutes(stored, key, project.id, day) != total:
        msg = f"row {row['entry_id']} not found verified on read-back"
        raise LedgerError(msg)
    return total - paid
