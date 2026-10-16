# Copyright (c) 2026 Krzysztof Rudnicki
"""Append-only, HMAC-signed trail of every add, remove, keep edit and import.

Nothing reads this to make a decision -- the CRDT log is the truth. It
exists so "when did I mark that day, and from which device" is answerable
later, and so a hand-edited line is detectable rather than invisible.

Signing is best-effort, as in freedays: with no key the line is written
unsigned, because an unsigned audit line is a much smaller problem than a
sick day that could not be taken because a key file was missing.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
import logging
from typing import TYPE_CHECKING, Any

from sickdays._day import to_iso
from sickdays._hmac import generate_key, sign
from sickdays._paths import Paths, resolve_paths

if TYPE_CHECKING:
    from datetime import date

_logger = logging.getLogger(__name__)


def record_event(
    action: str,
    day: date,
    *,
    actor: str,
    keep: frozenset[str] | None = None,
    paths: Paths | None = None,
) -> None:
    """Append one signed line describing a change to the pool.

    Args:
        action: ``"add"``, ``"remove"``, ``"keep"`` or ``"import"``.
        day: The day that changed.
        actor: The device id that made the change.
        keep: The day's kept lockers after the change, recorded (sorted)
            for an add or a keep edit; omitted from the line when ``None``.
        paths: Where the trail and its signing key live.
    """
    resolved = resolve_paths(paths)
    entry: dict[str, Any] = {
        "action": action,
        "day": to_iso(day),
        "actor": actor,
        "at": datetime.now(tz=UTC).isoformat(),
    }
    if keep is not None:
        entry["keep"] = sorted(keep)
    key_target = resolved.hmac_key
    if not key_target.exists():
        # First run on this machine: generating the key here means the trail
        # is signed from its first line, with no setup step to skip.
        generate_key(key_target)
    entry["hmac"] = sign(entry, key_file=key_target)
    target = resolved.audit
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
    except OSError as exc:
        # The change is already committed to the log; an unwritable trail
        # must never be the reason it fails.
        _logger.warning("could not append to the sick-day audit trail: %s", exc)
