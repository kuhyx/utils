# Copyright (c) 2026 Krzysztof Rudnicki
"""On-disk locations, remote paths and the one policy number that matters.

Every path here is a *default*. Public functions take the corresponding
argument and only fall back to these when it is ``None``, so tests can point
the whole package at a tmp_path and a bug in this package can never write
into real user state. See ``freedays/tests/conftest.py``, which redirects
these as a second line of defence.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

APP_NAME: Final = "freedays"

#: How many free days a calendar year grants. Resets on Jan 1; unused days do
#: not carry over. 35 sits in the middle of the 30-40 band this was specced
#: against -- roughly a week off per quarter plus a scattering of single days.
DEFAULT_ANNUAL_BUDGET: Final = 35

STATE_DIR: Final = Path.home() / ".local" / "share" / "freedays"

#: The CRDT log itself: date -> Record(state=free|cleared).
LOG_PATH: Final = STATE_DIR / "free_days.json"

#: crdt-sync's per-device push/pull bookkeeping. Never merged, purely local.
SYNC_STATE_PATH: Final = STATE_DIR / "sync_state.json"

#: This install's persisted uuid. Never a fixed "pc"/"phone" constant, so two
#: machines can never collide on one device directory.
DEVICE_ID_PATH: Final = STATE_DIR / "device_id"

#: Append-only HMAC-signed record of every mark/unmark, for after-the-fact
#: review. Not consulted by any decision -- the log above is the truth.
AUDIT_PATH: Final = STATE_DIR / "audit.jsonl"

#: Signing key for the audit trail, generated on first use.
#:
#: User-owned, unlike screen-locker's root-owned key under /etc. That key
#: defends the sick-day budget *against the person using the machine*, so it
#: has to live somewhere they cannot rewrite. Free days are the opposite:
#: they are theirs to take, no justification, no gatekeeper. The signature
#: here only answers "was this line edited after the fact", for their own
#: review -- so a per-user key is the right strength, and it means signing
#: works without root instead of warning on every single mark.
HMAC_KEY_FILE: Final = STATE_DIR / "hmac.key"

#: Remote layout, mirroring every other app: one directory per device under
#: a prefix, each device writing only its own file.
SYNC_PATH_PREFIX: Final = "freedays-sync/devices"
SYNC_FILENAME: Final = "free_days.json"

#: Field names inside a Record.
FIELD_STATE: Final = "state"
FIELD_ACTOR: Final = "actor"
FIELD_REASON: Final = "reason"

#: Sticky "this day arrived while it was free, so it is spent". Releasing a
#: *future* day refunds it -- it never happened. Releasing today or a past
#: day does not: the gates already stood down. Nothing ever writes this back
#: to false, which is what makes it monotonic under last-writer-wins merges.
FIELD_CONSUMED: Final = "consumed"

#: Values of FIELD_STATE. Un-marking flips the field rather than tombstoning
#: the record: crdt-sync deletes are deliberately monotonic, so a tombstoned
#: date could never be marked free again.
STATE_FREE: Final = "free"
STATE_CLEARED: Final = "cleared"
