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

Every credit row is written with a ``progress`` row in the same rename
(`record`): the review's share of the day's bonus is ``done`` of ``target``
(``earned_time`` 0.24.0, DOCS-progress.md). The target is frozen at the day's
first review; the facts are read back from the signed rows, never stored apart.

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
PROGRESS_SOURCE: Final = "review"
"""``earned_time``'s ``Earner.progress_source`` for the review top-up."""


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


def _signed(row: dict[str, Any], key: bytes) -> bool:
    """True when `row` carries the signature `entry_signature` gives it."""
    claim = row.get("hmac")
    return isinstance(claim, str) and hmac.compare_digest(
        claim, entry_signature(row, key)
    )


def _is_credit(row: dict[str, Any], day: str) -> bool:
    detail = row.get("detail")
    return (
        row.get("kind") == "credit"
        and row.get("day") == day
        and isinstance(detail, dict)
        and detail.get("source") == SOURCE
    )


def _fact(row: dict[str, Any], day: str) -> tuple[int, int] | None:
    """``(done, target)`` of a progress row about `day` for the review source."""
    detail = row.get("detail")
    if row.get("kind") != "progress" or not isinstance(detail, dict):
        return None
    done, target = detail.get("done"), detail.get("target")
    if (
        detail.get("source") != PROGRESS_SOURCE
        or detail.get("for_day") != day
        or not all(
            isinstance(v, str) and v.isascii() and v.isdigit() for v in (done, target)
        )
    ):
        return None
    return int(str(done)), int(str(target))


def _progress_row(
    rows: list[Any], key: bytes, day: str, due: int, moment: datetime
) -> dict[str, object] | None:
    """The row that makes the day's facts true, or None when they already are."""
    signed = [r for r in rows if isinstance(r, dict) and _signed(r, key)]
    facts = [f for r in signed if (f := _fact(r, day)) is not None]
    paid = sum(1 for r in signed if _is_credit(r, day))
    target = facts[0][1] if facts else max(due, paid, 1)
    state = (min(paid, target), target)
    if facts and facts[-1] == state:
        return None
    done = state[0]
    return {
        "entry_id": f"progress:{day}:{done}:{target}",
        "kind": "progress",
        "day": day,
        "created_at": moment.isoformat(),
        "amount": 0,
        "device": "pc",
        "detail": {
            "source": PROGRESS_SOURCE,
            "for_day": day,
            "done": str(done),
            "target": str(target),
        },
    }


def _credit_row(slug: str, cause: str, moment: datetime) -> dict[str, object]:
    return {
        "entry_id": ID_PREFIX + slug,
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


def record(slug: str, cause: str, *, due: int, now: datetime | None = None) -> bool:
    """Sign and append the rows for one finished review: credit plus progress.

    The progress row says "``done`` of ``target`` reviews for the day": ``done``
    is the day's signed review credits, capped at ``target``, which is `due`
    at the day's first progress row and never changes after it. Nothing is
    appended for a state the last progress row already says, and a slug that
    has its credit still gets the progress row it lacks (rows written before
    this writer existed), with ``max(due, credits)`` as the target.

    Args:
        slug: The reviewed problem.
        cause: The one named cause.
        due: How many reviews are due right now, this one included.
        now: The finish time, timezone-aware (default: now, local time).

    Returns:
        True when the credit row was written, False when the slug already had
        one.

    Raises:
        LedgerError: no key, an unreadable ledger or a failed write; nothing
            on disk changed, so neither row exists without the other.
    """
    key = _key()
    entries = _entries()
    moment = now or datetime.now(tz=UTC).astimezone()
    entry_id = ID_PREFIX + slug
    fresh = not any(
        isinstance(e, dict) and e.get("entry_id") == entry_id for e in entries
    )
    new: list[dict[str, object]] = []
    if fresh:
        credit = _credit_row(slug, cause, moment)
        credit["hmac"] = entry_signature(credit, key)
        new.append(credit)
    day = moment.date().isoformat()
    if (tally := _progress_row([*entries, *new], key, day, due, moment)) is not None:
        tally["hmac"] = entry_signature(tally, key)
        new.append(tally)
    if new:
        _write([*entries, *new])
    return fresh
