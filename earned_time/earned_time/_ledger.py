# Copyright (c) 2026 Krzysztof Rudnicki
"""The shared reader: did a gate's signed ledger record today's credit?

Every ledger-backed earner publishes the same way -- HMAC-signed ``credit``
rows in ``{"entries": [...]}`` -- so one reader serves all of them, with the
earner's ``match`` deciding which rows count. A new gate that writes that
shape needs no reader of its own in any consumer.

**Paths are always passed in.** The ledger and the key are resolved by the
consumer, never here: both consumers' test suites redirect their own module
constants, and a default living in this package would let a test read the
real ledger and the real key.

**"Cannot check" is not "no".** Every unreadable state returns ``None``. The
consumer fails closed to no bonus, but logs it -- failing open would let the
coupling be defeated by deleting a file.

The HMAC canonicalisation is gatelock's (``log_integrity.compute_entry_hmac``),
reproduced in stdlib instead of imported: gatelock pulls in tkinter, and the
root gaming daemon must be able to import this package headless.
"""

from __future__ import annotations

from datetime import UTC, datetime, time
import hashlib
import hmac
import json
import logging
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from earned_time._policy import Earner, Window

_logger: Final = logging.getLogger(__name__)

_CREDIT: Final = "credit"


def entry_signature(entry: dict[str, object], key: bytes) -> str:
    """The HMAC-SHA256 every locker signs a ledger row with.

    Args:
        entry: The row; any existing ``hmac`` field is left out.
        key: The shared signing key.

    Returns:
        The hex digest over the canonical JSON of the rest of the row.
    """
    body = {k: v for k, v in entry.items() if k != "hmac"}
    payload = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()


def verified(entry: dict[str, object], key: bytes) -> bool:
    """Whether a row's ``hmac`` is genuine. A forged credit earns time."""
    stored = entry.get("hmac")
    if not isinstance(stored, str):
        return False
    return hmac.compare_digest(stored, entry_signature(entry, key))


def today_window(now: datetime | None = None) -> tuple[float, float]:
    """Local midnight and now, as unix seconds: where today's credit must fall."""
    moment = (now or datetime.now(tz=UTC)).astimezone()
    midnight = datetime.combine(moment.date(), time.min, moment.tzinfo)
    return midnight.timestamp(), moment.timestamp()


def read_key(key_file: Path) -> bytes | None:
    """The signing key, or ``None`` (logged) when it is unreadable or empty."""
    try:
        key = key_file.read_bytes().strip()
    except OSError as exc:
        _logger.warning("Cannot read the integrity key at %s (%s)", key_file, exc)
        return None
    if not key:
        _logger.warning("Integrity key at %s is empty", key_file)
        return None
    return key


def read_rows(ledger: Path, earner: Earner) -> list[object] | None:
    """The ledger's ``entries`` array, or ``None`` when it cannot be read.

    A ledger that does not exist is ``[]`` -- silently -- for an earner whose
    gate may simply never have run (``missing_ledger_is_no``); for every other
    earner it is a fault like any unreadable file.
    """
    try:
        raw = json.loads(ledger.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        if earner.missing_ledger_is_no:
            return []
        _logger.warning(
            "Cannot read the %s ledger at %s (%s)", earner.label, ledger, exc
        )
        return None
    except OSError as exc:
        _logger.warning(
            "Cannot read the %s ledger at %s (%s)", earner.label, ledger, exc
        )
        return None
    except ValueError as exc:
        _logger.warning(
            "%s ledger at %s is not valid JSON (%s)", earner.label, ledger, exc
        )
        return None
    rows = raw.get("entries") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        _logger.warning("%s ledger at %s has no entries array", earner.label, ledger)
        return None
    return rows


def counting_rows(
    earner: Earner, ledger: Path, key_file: Path, window: Window
) -> Iterator[dict[str, object]] | None:
    """The verified ``credit`` rows that ``earner.match`` counts in ``window``.

    ``None`` when the key or the ledger cannot be read.

    Raises:
        ValueError: ``earner`` has no ``match``; its answer is the consumer's.
    """
    if earner.match is None:
        msg = f"earner {earner.name!r} has no shared reader; supply its answer"
        raise ValueError(msg)
    key = read_key(key_file)
    if key is None:
        return None
    rows = read_rows(ledger, earner)
    if rows is None:
        return None
    match = earner.match
    return (
        row
        for row in rows
        if isinstance(row, dict)
        and row.get("kind") == _CREDIT
        and verified(row, key)
        and match(row, window)
    )


def done_today(
    earner: Earner,
    ledger: Path,
    key_file: Path,
    *,
    now: datetime | None = None,
) -> bool | None:
    """Whether ``earner``'s ledger holds a verified credit that counts today.

    Args:
        earner: A ledger-backed earner (it must have ``match``).
        ledger: The gate's ledger file, resolved by the caller.
        key_file: The shared HMAC key, resolved by the caller.
        now: Stand-in for the current time, for tests.

    Returns:
        True or False when the ledger could be read and verified, ``None``
        when it could not -- which is never "not done".

    Raises:
        ValueError: ``earner`` has no ``match``; its answer is the consumer's.
    """
    rows = counting_rows(earner, ledger, key_file, today_window(now))
    if rows is None:
        return None
    return any(True for _ in rows)
