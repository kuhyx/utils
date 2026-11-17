# Copyright (c) 2026 Krzysztof Rudnicki
"""One ingest pass: RTDB and the local spool in, the board's reports out.

In: RTDB ``/<app>/errors/<device>/<id>`` and the spool. Out:
``<state>/app-errors/<app>.json``, the board's contract report.

RTDB entries are deleted once the state holding them is saved (``keep``
leaves them; ``seen`` stops a second count). kartka is skipped: it still runs
its own ingest (``~/src/kartka/tools/errors``), which the board reads through
its ``kartka`` adapter, and two readers of ``/kartka/errors`` would race.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import TYPE_CHECKING

from app_errors import spool, store
from app_errors.rtdb import RtdbError

if TYPE_CHECKING:
    from app_errors.rtdb import Rtdb

#: Apps with their own ingest, never read here (kartka moved over 2026-11-17).
SKIP_APPS: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Paths:
    """Where the ingest keeps its state, writes reports and reads the spool."""

    state: Path
    reports: Path
    spool: Path


@dataclass(frozen=True)
class Summary:
    """What one pass did."""

    merged: int
    rtdb_error: str | None


def default_paths() -> Paths:
    """Return the paths under ``$XDG_STATE_HOME`` (default ``~/.local/state``)."""
    base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
    return Paths(
        base / "app-errors-ingest" / "state.json",
        base / "app-errors",
        base / "app-errors-spool",
    )


def _rtdb_entries(
    db: Rtdb,
) -> tuple[list[tuple[str, str, object]], dict[str, dict[str, object]]]:
    """Return (app, device/id, entry) for every RTDB report, and the deletes that consume them."""
    found: list[tuple[str, str, object]] = []
    deletes: dict[str, dict[str, object]] = {}
    top = db.get("", shallow=True)
    for app in sorted(top) if isinstance(top, dict) else []:
        if app in SKIP_APPS or not store.APP_NAME.match(app):
            continue
        devices = db.get(f"{app}/errors")
        for device, entries in devices.items() if isinstance(devices, dict) else []:
            for entry_id, entry in entries.items() if isinstance(entries, dict) else []:
                found.append((app, f"{device}/{entry_id}", entry))
                deletes.setdefault(app, {})[f"{device}/{entry_id}"] = None
    return found, deletes


def run(paths: Paths, db: Rtdb | None, *, keep: bool = False) -> Summary:
    """Ingest everything once; RTDB failures are returned, the spool still goes in."""
    state = store.load(paths.state)
    merged = 0
    rtdb_error = None
    deletes: dict[str, dict[str, object]] = {}
    if db is not None:
        try:
            found, deletes = _rtdb_entries(db)
        except RtdbError as e:
            found, rtdb_error = [], str(e)
        merged += sum(store.merge(state, app, key, entry) for app, key, entry in found)
    merged += sum(store.merge(state, line.app, line.id, line.entry) for line in spool.drain(paths.spool))
    store.save(paths.state, state)
    store.write_reports(paths.reports, state)
    if db is not None and not keep:
        try:
            for app, paths_gone in deletes.items():
                db.patch(f"{app}/errors", paths_gone)
        except RtdbError as e:
            rtdb_error = str(e)
    return Summary(merged, rtdb_error)
