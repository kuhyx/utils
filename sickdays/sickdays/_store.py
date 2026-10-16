# Copyright (c) 2026 Krzysztof Rudnicki
"""Reading and writing the pool file, failing closed and loudly.

``crdt_sync.read_log`` is deliberately not used for reading: it turns a
corrupt file into an empty log *silently*, and lets a ``PermissionError``
escape. A gate asking "is today a sick day?" must never raise, and an
unreadable pool must be visible in the journal -- it silently re-arms every
lock and alarm, which is the safe direction but a confusing one.

So there are two readers. :func:`read_pool` is for gates: anything wrong
reads as "no sick days" and is logged. :func:`read_pool_strict` is for
writers: a file that exists but cannot be parsed raises, because rewriting
it from an empty pool would destroy whatever it still holds.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from crdt_sync import load_log, write_log

from sickdays._errors import UnreadablePoolError

if TYPE_CHECKING:
    from pathlib import Path

    from crdt_sync import Log

_logger = logging.getLogger(__name__)


def _read(path: Path) -> Log:
    """Parse ``path``; ``{}`` when missing. Raises on anything else."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError as exc:
        msg = f"the sick-day pool {path} cannot be read: {exc}"
        raise UnreadablePoolError(msg) from exc
    try:
        return load_log(text)
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        msg = f"the sick-day pool {path} is corrupt: {exc!r}"
        raise UnreadablePoolError(msg) from exc


def read_pool(path: Path) -> Log:
    """Return the pool at ``path``; empty (and logged) when it is unusable.

    A missing file is the normal "no sick day was ever taken" and is not
    logged. Anything else -- unreadable, unparsable, wrong shape -- is a
    warning, and reads as *no sick days*: the gates apply.
    """
    try:
        return _read(path)
    except UnreadablePoolError as exc:
        _logger.warning("%s -- treating every day as NOT a sick day", exc)
        return {}


def read_pool_strict(path: Path) -> Log:
    """Return the pool at ``path``, or raise if it exists but is unusable.

    Raises:
        UnreadablePoolError: The file exists but cannot be read or parsed.
    """
    return _read(path)


def write_pool(path: Path, log: Log) -> None:
    """Write ``log`` to ``path`` atomically (crdt-sync's temp-then-rename)."""
    write_log(path, log)
