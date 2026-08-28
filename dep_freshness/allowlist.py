"""Parse and validate `dependency-freshness.allowlist.yaml`.

Two entry classes, and the distinction is the whole point:

* `blocked_by: transitive:<pkg>@<ver>` is a **predicate**. The blocker is
  re-evaluated every run and the entry clears itself when upstream moves. It
  never expires on a calendar, because a date nobody can act on turns the gate
  red for a reason no commit can fix.
* anything else is **discretionary**: it needs `expires`, capped at 90 days,
  and fails once past.

Malformed, expired, over-cap and no-longer-needed entries all exit 2 — an
allowlist that rots silently is a suppression, not an exception.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import yaml

from dep_freshness._tables import ALLOWLIST_FILE, ALLOWLIST_MAX_DAYS
from dep_freshness.models import Exception_

REQUIRED = ("ecosystem", "package", "pinned", "reason", "blocked_by")


class AllowlistError(Exception):
    """The allowlist itself is wrong; the gate refuses to run against it."""


def path_for(root: Path) -> Path:
    return root / ALLOWLIST_FILE


def _parse_date(raw: object, where: str) -> date:
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    try:
        return datetime.strptime(str(raw), "%Y-%m-%d").date()
    except ValueError as exc:
        raise AllowlistError(f"{where}: expires must be YYYY-MM-DD, got {raw!r}") from exc


def _entry(raw: object, source: Path, position: int) -> Exception_:
    where = f"{source}: exceptions[{position}]"
    if not isinstance(raw, dict):
        raise AllowlistError(f"{where}: each exception must be a mapping")
    missing = [field for field in REQUIRED if not str(raw.get(field, "")).strip()]
    if missing:
        raise AllowlistError(f"{where}: missing required field(s): {', '.join(missing)}")
    entry = Exception_(
        ecosystem=str(raw["ecosystem"]).strip(),
        package=str(raw["package"]).strip(),
        pinned=str(raw["pinned"]).strip(),
        reason=str(raw["reason"]).strip(),
        blocked_by=str(raw["blocked_by"]).strip(),
        latest_known=(str(raw["latest_known"]).strip()
                      if raw.get("latest_known") else None),
        expires=(str(raw["expires"]).strip() if raw.get("expires") else None),
        source=source,
    )
    if entry.transitive:
        if entry.expires:
            raise AllowlistError(
                f"{where}: a transitive: entry must NOT set expires -- it clears "
                "itself when the blocker lifts, and a date nobody can act on "
                "only turns the gate red for no actionable reason"
            )
        if not entry.blocker or not all(entry.blocker):
            raise AllowlistError(
                f"{where}: blocked_by must read transitive:<package>@<version>"
            )
        return entry
    if not entry.expires:
        raise AllowlistError(f"{where}: a discretionary entry requires expires")
    return entry


def check_expiry(entry: Exception_, today: date | None = None) -> None:
    """Raise if a discretionary entry is past due or reaches too far out."""
    if entry.transitive or not entry.expires:
        return
    now = today or date.today()
    when = _parse_date(entry.expires, f"{entry.source}: {entry.package}")
    if when < now:
        raise AllowlistError(
            f"{entry.source}: {entry.ecosystem}:{entry.package} expired on {when}"
        )
    if (when - now).days > ALLOWLIST_MAX_DAYS:
        raise AllowlistError(
            f"{entry.source}: {entry.ecosystem}:{entry.package} expires {when}, "
            f"more than {ALLOWLIST_MAX_DAYS} days out"
        )


def load(root: Path) -> list[Exception_]:
    """Every exception declared for `root`; [] when there is no allowlist."""
    source = path_for(root)
    if not source.is_file():
        return []
    try:
        data = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise AllowlistError(f"{source}: unreadable ({exc})") from exc
    if data is None:
        return []
    if not isinstance(data, dict) or "exceptions" not in data:
        raise AllowlistError(f"{source}: expected a top-level 'exceptions:' list")
    raw_entries = data.get("exceptions") or []
    if not isinstance(raw_entries, list):
        raise AllowlistError(f"{source}: 'exceptions' must be a list")
    entries = [_entry(raw, source, i) for i, raw in enumerate(raw_entries)]
    for entry in entries:
        check_expiry(entry)
    return entries
