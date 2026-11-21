"""The coach's OWN signed ledger: one row per finished review.

``~/.local/share/leetcode-coach/review_ledger.json``, laid out like the
guard's ledger (``{"version": 1, "entries": [...]}``) so ``earned_time``'s
verified-row reader can read it. It is a separate file on purpose: nothing in
the coach may reach the guard's ledger (`relay/__init__.py`).

A row is signed the way every locker signs: HMAC-SHA256 over the canonical
JSON of the row without ``hmac``, keyed with ``/etc/workout-locker/hmac.key``.
`entry_signature` repeats ``earned_time.entry_signature``'s three lines, since
the coach does not depend on ``earned_time``;
``test_earned_time_verifies_the_row_and_signs_it_the_same`` holds the two
together.

Fail closed: without a readable key, or over a ledger file that does not
parse, `record` raises `LedgerError` and writes nothing. Each slug gets one row
ever. The write is a rename over the target, so a crash leaves the old file.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import tempfile
from typing import Any, Final

_LOG: Final = logging.getLogger(__name__)

LEDGER_PATH: Final = (
    Path.home() / ".local" / "share" / "leetcode-coach" / "review_ledger.json"
)
KEY_FILE: Final = Path("/etc/workout-locker/hmac.key")
VERSION: Final = 1
"""The guard ledger's ``_ledger_io._VERSION``."""
SOURCE: Final = "leetcode-coach-review"
ID_PREFIX: Final = "review:"


class LedgerError(RuntimeError):
    """No signed row could be written; nothing on disk changed."""


def entry_signature(entry: dict[str, object], key: bytes) -> str:
    """The HMAC-SHA256 every locker signs a ledger row with (``hmac`` left out)."""
    body = {k: v for k, v in entry.items() if k != "hmac"}
    payload = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()


def _key() -> bytes:
    try:
        key = KEY_FILE.read_bytes().strip()
    except OSError as exc:
        _LOG.warning("cannot read the signing key at %s: %s", KEY_FILE, exc)
        msg = f"cannot read the signing key at {KEY_FILE}: {exc}"
        raise LedgerError(msg) from exc
    if not key:
        _LOG.warning("the signing key at %s is empty", KEY_FILE)
        msg = f"the signing key at {KEY_FILE} is empty"
        raise LedgerError(msg)
    return key


def _entries() -> list[Any]:
    """The rows on disk; none while the file does not exist yet."""
    if not LEDGER_PATH.exists():
        return []
    try:
        data = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _LOG.warning("review ledger %s is unreadable: %s", LEDGER_PATH, exc)
        msg = f"the review ledger at {LEDGER_PATH} is unreadable, not overwritten"
        raise LedgerError(msg) from exc
    entries = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        _LOG.warning("review ledger %s has no entries list", LEDGER_PATH)
        msg = f"the review ledger at {LEDGER_PATH} has no entries, not overwritten"
        raise LedgerError(msg)
    return entries


def _write(entries: list[Any]) -> None:
    text = json.dumps({"version": VERSION, "entries": entries}, indent=2) + "\n"
    folder = LEDGER_PATH.parent
    try:
        folder.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=folder, prefix=".review-", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        Path(tmp).replace(LEDGER_PATH)
    except OSError as exc:
        _LOG.warning("review ledger %s not written: %s", LEDGER_PATH, exc)
        msg = f"cannot write the review ledger at {LEDGER_PATH}: {exc}"
        raise LedgerError(msg) from exc


def record(slug: str, cause: str, *, now: datetime | None = None) -> bool:
    """Sign and append the row for one finished review.

    Args:
        slug: The reviewed problem.
        cause: The one named cause.
        now: The finish time, timezone-aware (default: now, local time).

    Returns:
        True when the row was written, False when the slug already had one.

    Raises:
        LedgerError: no key, an unreadable ledger or a failed write; nothing
            on disk changed.
    """
    key = _key()
    entries = _entries()
    entry_id = ID_PREFIX + slug
    if any(isinstance(e, dict) and e.get("entry_id") == entry_id for e in entries):
        return False
    moment = now or datetime.now(tz=UTC).astimezone()
    row: dict[str, object] = {
        "entry_id": entry_id,
        "kind": "credit",
        "day": moment.date().isoformat(),
        "created_at": moment.isoformat(),
        "amount": 1,
        "device": "pc",
        "detail": {
            "title_slug": slug,
            "cause": cause,
            "source": SOURCE,
            "finished_at": str(int(moment.timestamp())),
        },
    }
    row["hmac"] = entry_signature(row, key)
    _write([*entries, row])
    return True
