# Copyright (c) 2026 Krzysztof Rudnicki
"""On-disk locations, remote paths and record field names.

Every path here is a *default*. Public functions take the corresponding
argument and only fall back to these when it is ``None``, so tests can point
the whole package at a tmp_path and a bug in this package can never write
into real user state. See ``sickdays/tests/conftest.py``, which redirects
these as a second line of defence.

Nothing here is shared with freedays. The two pools are different things
with different names, so they never share a directory, a file or a remote
node -- a sync bug in one can never touch the other.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

APP_NAME: Final = "sickdays"

STATE_DIR: Final = Path.home() / ".local" / "share" / "sickdays"

#: The CRDT log itself: ISO date -> Record(state=sick|cleared).
LOG_PATH: Final = STATE_DIR / "sick_days.json"

#: crdt-sync's per-device push/pull bookkeeping. Never merged, purely local.
SYNC_STATE_PATH: Final = STATE_DIR / "sync_state.json"

#: This install's persisted uuid. Never a fixed "pc"/"phone" constant, so two
#: machines can never collide on one device directory.
DEVICE_ID_PATH: Final = STATE_DIR / "device_id"

#: Append-only HMAC-signed record of every add/remove/import, for
#: after-the-fact review. Not consulted by any decision -- the log is the truth.
AUDIT_PATH: Final = STATE_DIR / "audit.jsonl"

#: Signing key for the audit trail, generated on first use. User-owned, as in
#: freedays: the signature answers "was this line edited after the fact" for
#: the person's own review, it does not defend a budget (there is none).
HMAC_KEY_FILE: Final = STATE_DIR / "hmac.key"

#: Remote layout, mirroring every other app: one directory per device under
#: a prefix, each device writing only its own file.
SYNC_PATH_PREFIX: Final = "sickdays-sync/devices"
SYNC_FILENAME: Final = "sick_days.json"

#: Field names inside a Record.
FIELD_STATE: Final = "state"
FIELD_ACTOR: Final = "actor"
#: The sorted, de-duplicated list of locker ids that stay active on the day
#: (0.2.0). Absent on every 0.1.0 record, which reads as "keep nothing".
FIELD_KEEP: Final = "keep"

#: Values of FIELD_STATE. Removing flips the field rather than tombstoning
#: the record: crdt-sync deletes are monotonic (OR-merged), so a tombstoned
#: date could never be marked sick again.
STATE_SICK: Final = "sick"
STATE_CLEARED: Final = "cleared"

#: Locker ids a sick day may keep active (``FIELD_KEEP``). A locker *stands
#: down* on a day iff the day is sick and the locker is not in its keep set.
#: These strings are wire format: the phone writes the same ones.
LOCKER_WORKOUT: Final = "workout"
LOCKER_LEETCODE: Final = "leetcode"
LOCKER_BOOK: Final = "book"
LOCKER_DIET: Final = "diet"
#: The phone ring, the PC fallback ring, the RTC self-wake and the
#: missed-alarm penalty -- one switch, because they are one alarm.
LOCKER_ALARM: Final = "alarm"
LOCKERS: Final = (
    LOCKER_WORKOUT,
    LOCKER_LEETCODE,
    LOCKER_BOOK,
    LOCKER_DIET,
    LOCKER_ALARM,
)
