# Copyright (c) 2026 Krzysztof Rudnicki
"""Read the morning-session carrot wake-alarm signed for today.

The phone's morning (weigh-in, shower, dress, desk) is published to the PC
and distilled by wake-alarm into ``morning_session.json``, HMAC-signed, always
dated today, with an ``exempt_until`` while the morning is live or once it was
completed in time (11:00). Every gate that honours the carrot reads it here.
This module never re-derives that policy: the whole decision is *signature
ok, dated today, now < exempt_until*. Missing, stale, failed or tampered all
mean "no skip" -- the gate runs as it always has.

A run deferral, never ledger state: nothing is written, so a deleted file
cannot mint an unlocked day.

The one wrinkle is a PC booted mid-morning: the file is missing or yesterday's
until wake-alarm's ``Persistent=true`` timer catches up, which needs the
network. The arming run waits for that, bounded; status paths never do.

The path and the retry budget are parameters, not module state, so each
consumer's test suite keeps redirecting its own constant.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import logging
from pathlib import Path
import time
from typing import TYPE_CHECKING, Final

from gatelock.log_integrity import verify_entry_hmac

if TYPE_CHECKING:
    from collections.abc import Callable

_logger = logging.getLogger(__name__)

MORNING_SESSION_FILE: Final = (
    Path.home() / ".local" / "state" / "wake_alarm" / "morning_session.json"
)
"""Where wake-alarm writes it. Keep in step with ``wake_alarm/_constants.py``."""

# Only inside this local window is a non-today file worth waiting for: the
# refresher runs 05:00-11:00, so outside it "not today's" is simply the truth.
MORNING_WINDOW: Final = ((5, 0), (11, 0))
MORNING_RETRY_SECONDS: Final = 30.0
MORNING_POLL_SECONDS: Final = 5.0


@dataclass(frozen=True)
class MorningSkip:
    """A skip the morning session earned: what the phone said, and until when."""

    outcome: str
    exempt_until: datetime

    def __str__(self) -> str:
        """Say which morning earned it and when the gate comes back."""
        return f"{self.outcome} session, no lock until {self.exempt_until:%H:%M}"


def _read_verified(path: Path) -> dict[str, object] | None:
    """The file's entry when it exists, parses and verifies; else None.

    Missing is debug (it is the normal state outside the morning); anything
    else is a warning, because it means the refresher or the key is broken.
    """
    if not path.exists():
        _logger.debug("No morning session file at %s", path)
        return None
    try:
        entry = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        _logger.warning("Cannot read %s: %s", path, exc)
        return None
    if not isinstance(entry, dict) or not verify_entry_hmac(entry):
        _logger.warning("Morning session file is not a signed object")
        return None
    return entry


def _load_today(path: Path, now: datetime) -> dict[str, object] | None:
    """Today's verified entry, or None. ``now`` is already local."""
    entry = _read_verified(path)
    if entry is None or entry.get("date") != now.date().isoformat():
        return None
    return entry


def _skip_from(entry: dict[str, object], now: datetime) -> MorningSkip | None:
    """The skip an entry grants at ``now``, if its window is still open."""
    until = entry.get("exempt_until")
    if not isinstance(until, str):
        return None
    try:
        exempt_until = datetime.fromisoformat(until)
    except ValueError:
        _logger.warning("Morning session exempt_until unreadable: %r", until)
        return None
    if exempt_until.tzinfo is None or now >= exempt_until:
        # A naive instant cannot be compared with a local one, and guessing
        # its zone would be inventing a carrot the signer never granted.
        return None
    return MorningSkip(outcome=str(entry.get("outcome")), exempt_until=exempt_until)


def _in_window(now: datetime) -> bool:
    (start_h, start_m), (end_h, end_m) = MORNING_WINDOW
    minutes = now.hour * 60 + now.minute
    return start_h * 60 + start_m <= minutes < end_h * 60 + end_m


def _local_now() -> datetime:
    return datetime.now(tz=UTC).astimezone()


def morning_skip(
    path: Path = MORNING_SESSION_FILE,
    now: datetime | None = None,
    *,
    wait: bool,
    retry_seconds: float = MORNING_RETRY_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> MorningSkip | None:
    """The skip the morning session earned at ``now``, or None.

    With ``wait`` (the arming path only), a file that is not today's during
    the morning window is retried for up to ``retry_seconds`` so a freshly
    booted PC gives wake-alarm's catch-up run a chance to land.
    """
    now = (now or _local_now()).astimezone()
    entry = _load_today(path, now)
    waited = 0.0
    while entry is None and wait and _in_window(now) and waited < retry_seconds:
        sleep(MORNING_POLL_SECONDS)
        waited += MORNING_POLL_SECONDS
        now = _local_now()
        entry = _load_today(path, now)
    if entry is None:
        if waited:
            _logger.warning(
                "No morning session for today after %.0fs; "
                "is wake-alarm-session.timer running?",
                waited,
            )
        return None
    return _skip_from(entry, now)
