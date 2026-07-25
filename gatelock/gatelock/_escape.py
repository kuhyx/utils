"""A sanctioned, rate-limited way out of a lock.

A hard lock without an escape hatch is a trap. screen-locker learned this and
grew "sick mode": you cannot always do the workout, so there is a bounded,
justified, tamper-evident way to say so. diet-guard's exit is cheap by nature
(log a meal). wake-alarm had neither -- its only exit was solving four
challenges in a row, which is a poor thing to require of someone who has just
woken up, and no exit at all if the alarm misfires at the wrong hour.

This module is the generic core of that hatch, so every app gets the *same*
mechanism instead of a copy that drifts:

* **Rolling budgets.** Once any window is exhausted the hatch disappears
  entirely -- it is not a slider, it is a hard stop.
* **Escalating lockout.** Each recent use doubles the wait, so the hatch gets
  progressively less convenient than just doing the thing.
* **A written justification.** Long enough to be inconvenient to invent, shown
  back to you next time so recycled excuses are visible.
* **Tamper evidence.** Every entry is HMAC-signed with a root-owned key, so
  hand-editing the history is detectable.

App-specific policy stays with the app: screen-locker's commitment penalty and
workout debt are not general, and are deliberately not modelled here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
import logging
from typing import TYPE_CHECKING, Any

from gatelock.log_integrity import compute_entry_hmac, verify_entry_hmac

if TYPE_CHECKING:
    from pathlib import Path

_logger = logging.getLogger(__name__)

_DATE_FORMAT = "%Y-%m-%d"

# The severity scale the dialog presents.
_MIN_SEVERITY = 1
_MAX_SEVERITY = 10


@dataclass(frozen=True)
class EscapePolicy:
    """How hard one app's escape hatch is to use.

    Defaults mirror screen-locker's sick mode, which is the proven shape.

    Attributes:
        name: Short identifier used in logs and the summary line.
        label: Human wording for one use, e.g. "sick day".
        budget_per_7_days: Uses allowed in a rolling week.
        budget_per_30_days: Uses allowed in a rolling month.
        budget_per_90_days: Uses allowed in a rolling quarter.
        lockout_seconds: Base wait before the hatch actually opens.
        lockout_multiplier_per_recent: Wait multiplier per use in 30 days.
        justification_min_chars: Minimum length of the written reason.
        history_review_count: How many past reasons to show back to the user.
    """

    name: str
    label: str
    budget_per_7_days: int = 1
    budget_per_30_days: int = 3
    budget_per_90_days: int = 10
    lockout_seconds: int = 120
    lockout_multiplier_per_recent: int = 2
    justification_min_chars: int = 120
    history_review_count: int = 10


@dataclass
class EscapeHistory:
    """Persistent record of every use of one app's hatch."""

    used_days: list[str] = field(default_factory=list)
    justifications: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class EscapeDraft:
    """A proposed use of the hatch, before validation."""

    reason: str
    onset: str
    severity: int
    description: str


def _today_iso() -> str:
    """Return today's date as ``YYYY-MM-DD`` (UTC)."""
    return datetime.now(tz=timezone.utc).strftime(_DATE_FORMAT)


def _parse_iso(date_str: str) -> datetime | None:
    """Parse ``YYYY-MM-DD`` into a UTC datetime, or None if unparsable.

    An unparsable entry is *ignored* rather than fatal, but logged loudly:
    silently counting it as zero would quietly widen the budget.
    """
    try:
        return datetime.strptime(date_str, _DATE_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        _logger.warning(
            "escape history holds an unparsable date %r (%s) -- that entry is "
            "IGNORED when counting against the budget",
            date_str,
            exc,
        )
        return None


class EscapeTracker:
    """Budget, lockout and tamper-evident history for one app's hatch."""

    def __init__(
        self,
        policy: EscapePolicy,
        path: Path,
        *,
        key_file: Path | None = None,
    ) -> None:
        """Bind a policy to the file its history lives in."""
        self._policy = policy
        self._path = path
        self._key_file = key_file
        self.history = EscapeHistory()
        self.tampered = 0
        """How many loaded entries failed their integrity check."""

    @property
    def policy(self) -> EscapePolicy:
        """The policy this tracker enforces."""
        return self._policy

    def load(self) -> EscapeHistory:
        """Read history from disk, tolerating a missing or corrupt file.

        **Integrity problems never reduce recorded usage.** An entry that
        fails its HMAC check is kept for budget counting and reported loudly,
        rather than dropped. Dropping would be the intuitive move and is
        exactly wrong: ``verify_entry_hmac`` also returns False when the key
        file is merely *unreadable*, so "drop what you cannot verify" would
        turn a chmod on the key into an unlimited escape hatch. Tampering is
        something to shout about, not something that should widen the budget.
        """
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            self.history = EscapeHistory()
            return self.history
        except (OSError, json.JSONDecodeError) as exc:
            _logger.warning("could not read escape history %s: %s", self._path, exc)
            self.history = EscapeHistory()
            return self.history
        if not isinstance(raw, dict):
            self.history = EscapeHistory()
            return self.history
        justifications = [
            entry for entry in raw.get("justifications", []) if isinstance(entry, dict)
        ]
        self.tampered = sum(1 for entry in justifications if not self._verified(entry))
        self.history = EscapeHistory(
            used_days=[d for d in raw.get("used_days", []) if isinstance(d, str)],
            justifications=justifications,
        )
        return self.history

    def _verified(self, entry: dict[str, Any]) -> bool:
        """Whether an entry's HMAC still matches its contents.

        A failure is reported, never acted on by discarding the entry -- see
        :meth:`load`.
        """
        if verify_entry_hmac(entry, key_file=self._key_file):
            return True
        _logger.error(
            "escape history entry dated %r failed its HMAC check -- the file "
            "has been edited outside the app, or the signing key is "
            "unreadable. The entry still counts against the budget.",
            entry.get("date", "?"),
        )
        return False

    def save(self) -> bool:
        """Write history back to disk. False if it could not be written."""
        payload = {
            "used_days": self.history.used_days,
            "justifications": self.history.justifications,
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError:
            _logger.exception("could not save escape history %s", self._path)
            return False
        return True

    def count_in_window(self, days: int, *, today: str | None = None) -> int:
        """How many uses fall in the trailing ``days`` window."""
        today_str = today or _today_iso()
        today_dt = _parse_iso(today_str)
        if today_dt is None:
            return 0
        cutoff = today_dt - timedelta(days=days)
        count = 0
        for entry in self.history.used_days:
            parsed = _parse_iso(entry)
            if parsed is not None and cutoff < parsed <= today_dt:
                count += 1
        return count

    def is_budget_exhausted(self, *, today: str | None = None) -> bool:
        """Whether any rolling window has reached its limit.

        When True the app must not offer the hatch at all -- not offer it
        greyed out, not offer it with a longer wait. Gone.
        """
        policy = self._policy
        return (
            self.count_in_window(7, today=today) >= policy.budget_per_7_days
            or self.count_in_window(30, today=today) >= policy.budget_per_30_days
            or self.count_in_window(90, today=today) >= policy.budget_per_90_days
        )

    def compute_lockout_seconds(self, *, today: str | None = None) -> int:
        """Escalating wait: ``base * multiplier ** uses_in_30_days``."""
        recent = self.count_in_window(30, today=today)
        multiplier: int = self._policy.lockout_multiplier_per_recent**recent
        return int(self._policy.lockout_seconds * multiplier)

    def budget_summary(self, *, today: str | None = None) -> str:
        """One-line summary of remaining budget, for the dialog."""
        policy = self._policy
        week = self.count_in_window(7, today=today)
        month = self.count_in_window(30, today=today)
        quarter = self.count_in_window(90, today=today)
        return (
            f"{policy.label}: {week}/{policy.budget_per_7_days}w · "
            f"{month}/{policy.budget_per_30_days}m · "
            f"{quarter}/{policy.budget_per_90_days}q"
        )

    def validate(self, draft: EscapeDraft) -> str | None:
        """Return a user-facing complaint about ``draft``, or None if valid."""
        if not draft.reason.strip():
            return "Say what the problem is."
        if not draft.onset.strip():
            return "Say when it started."
        if not _MIN_SEVERITY <= draft.severity <= _MAX_SEVERITY:
            return f"Severity must be between {_MIN_SEVERITY} and {_MAX_SEVERITY}."
        minimum = self._policy.justification_min_chars
        if len(draft.description.strip()) < minimum:
            written = len(draft.description.strip())
            return f"Explain properly: {written}/{minimum} characters."
        return None

    def record(self, draft: EscapeDraft, *, today: str | None = None) -> bool:
        """Sign and append a use of the hatch. False if it could not be saved."""
        today_str = today or _today_iso()
        entry: dict[str, Any] = {
            "date": today_str,
            "policy": self._policy.name,
            "reason": draft.reason.strip(),
            "onset": draft.onset.strip(),
            "severity": draft.severity,
            "description": draft.description.strip(),
        }
        signature = compute_entry_hmac(entry, key_file=self._key_file)
        if signature is not None:
            entry["hmac"] = signature
        self.history.justifications.append(entry)
        if today_str not in self.history.used_days:
            self.history.used_days.append(today_str)
        return self.save()

    def recent_justifications(self, count: int | None = None) -> list[dict[str, Any]]:
        """The most recent justifications, newest last."""
        limit = count if count is not None else self._policy.history_review_count
        return self.history.justifications[-limit:]

    def format_recent(self, count: int | None = None) -> str:
        """Render past justifications for read-back in the dialog.

        Showing these is half the deterrent: a recycled excuse is obvious when
        the last ten are on screen above the form.
        """
        entries = self.recent_justifications(count)
        if not entries:
            return "(no previous uses)"
        return "\n".join(
            f"{entry.get('date', '?')}  [{entry.get('severity', '?')}/10] "
            f"{entry.get('reason', '')}: {entry.get('description', '')[:120]}"
            for entry in entries
        )
