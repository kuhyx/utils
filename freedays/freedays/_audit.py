"""Append-only, HMAC-signed trail of every mark and release.

Nothing reads this to make a decision -- the CRDT log is the truth, and this
file is deliberately not consulted by :mod:`freedays._api`. It exists so that
"when did I take that day, and from which device" is answerable later, and so
that a hand-edited entry is detectable rather than invisible.

Signing is best-effort on purpose. If the key is missing the entry is still
written, unsigned: an unsigned audit line is a much smaller problem than a
free day that could not be claimed because a key file was absent.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
import logging
from typing import TYPE_CHECKING, Any

from gatelock.log_integrity import compute_entry_hmac, generate_hmac_key

from freedays._day import to_iso
from freedays._paths import Paths, resolve_paths

if TYPE_CHECKING:
    from datetime import date

_logger = logging.getLogger(__name__)


def record_event(
    action: str,
    day: date,
    *,
    actor: str,
    reason: str = "",
    paths: Paths | None = None,
) -> None:
    """Append one signed line describing a change to the pool.

    Args:
        action: ``"mark"`` or ``"release"``.
        day: The day that changed.
        actor: The device id that made the change.
        reason: Optional free text supplied by the person.
        paths: Where the trail and its signing key live.
    """
    resolved = resolve_paths(paths)
    entry: dict[str, Any] = {
        "action": action,
        "day": to_iso(day),
        "actor": actor,
        "reason": reason,
        "at": datetime.now(tz=UTC).isoformat(),
    }
    key_target = resolved.hmac_key
    if not key_target.exists():
        # First run on this machine. Generating it here rather than in an
        # installer means the trail is signed from the very first entry, and
        # that gatelock never gets to warn about a key that was simply never
        # created yet.
        key_target.parent.mkdir(parents=True, exist_ok=True)
        generate_hmac_key(key_target)
        key_target.chmod(0o600)
    entry["hmac"] = compute_entry_hmac(entry, key_file=key_target)
    target = resolved.audit
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
    except OSError as exc:
        # An unwritable audit trail must never be the reason a day cannot be
        # taken -- the caller has already committed the change to the log.
        _logger.warning("could not append to the free-day audit trail: %s", exc)
