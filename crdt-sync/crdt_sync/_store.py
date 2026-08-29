"""Local JSON persistence for a ``Log``.

Mirrors ``crdt_sync_dart``'s ``logToJson``/``FileLogPersistence`` serialization
so a log written by the Dart side parses here and vice versa. Deliberately
*non-reactive*: the change-stream/reactive store is a Dart/Flutter-only
convenience (it exists to drive a live UI). On the Python side, where consumers
are headless sync ticks, this is plain load and (atomic) save.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

from crdt_sync._record import Record

if TYPE_CHECKING:
    from pathlib import Path

    from crdt_sync._log import Log


def dump_log(log: Log) -> str:
    """Serialize ``log`` to canonical JSON text (id -> record dict)."""
    return json.dumps({rid: record.to_dict() for rid, record in log.items()})


def load_log(text: str) -> Log:
    """Parse text produced by :func:`dump_log` back into a ``Log``.

    Raises ``ValueError`` (bad JSON), ``KeyError`` or ``TypeError`` (valid
    JSON, wrong shape) on a corrupt payload -- callers reading from disk go
    through :func:`read_log`, which turns those into an empty log.
    """
    raw = json.loads(text)
    if not isinstance(raw, dict):
        msg = f"expected a JSON object mapping id -> record, got {type(raw).__name__}"
        raise TypeError(msg)
    return {rid: Record.from_dict(value) for rid, value in raw.items()}


def read_log(path: Path) -> Log:
    """Read a ``Log`` from ``path``; empty on a missing or unparsable file.

    A truncated or corrupt file can never raise here: it is treated as "no log
    yet", matching the Dart store's defensive load so a half-written file can't
    brick a consumer.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    try:
        return load_log(text)
    except ValueError, KeyError, TypeError:
        return {}


def write_log(path: Path, log: Log) -> None:
    """Write ``log`` to ``path`` atomically (temp file then rename).

    Writes to a per-process temp file and ``replace``s it over the real path,
    so a concurrent reader never observes a half-written file. Mirrors the
    Dart ``FileLogPersistence`` write scheme.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(dump_log(log), encoding="utf-8")
    tmp.replace(path)
