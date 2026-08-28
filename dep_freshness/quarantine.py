"""What is the newest npm version the package manager will actually install?

pnpm 11 refuses any package published inside its `minimumReleaseAge` window --
a supply-chain measure that blunts the period during which a compromised
publish is live. Reporting a repo as "behind" a version pnpm would reject is a
finding nobody can act on, so the gate's notion of latest is narrowed to match.

Cost is the reason this is a separate pass rather than part of `npmjs.latest`.
Publish timestamps live only in the FULL registry document, which is 7MB for
react and 16MB for typescript, against 3MB and 9MB abbreviated. So the full
document is fetched only when a finding already exists -- in the steady state,
where everything is current, that is zero extra requests.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from dep_freshness._tables import NPM_API, NPM_QUARANTINE_HOURS
from dep_freshness.registries.http import Offline, get_json
from dep_freshness.versions import newest_stable, parse


def cutoff(now: datetime | None = None) -> datetime:
    """Publishes at or after this instant are still quarantined."""
    moment = now or datetime.now(timezone.utc)
    return moment - timedelta(hours=NPM_QUARANTINE_HOURS)


def _parse(stamp: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def installable_latest(
    name: str, ceiling: str, now: datetime | None = None
) -> str | None:
    """Newest stable release published before the quarantine cutoff.

    `ceiling` is the registry's `dist-tags.latest`, and candidates above it are
    ignored. npm lets a maintainer publish a version without tagging it
    `latest` -- a maintenance-line release on an older major, say -- so the
    highest version NUMBER is not always the current release. Falling back to
    the numeric maximum here would recommend a version npm does not consider
    current, and would disagree with `npmjs.latest`, which honours the tag.

    Returns None when the answer cannot be determined (offline, or the
    registry has no `time` map), which callers must treat as "no change" --
    narrowing on a guess would hide a genuinely stale dependency.
    """
    url = NPM_API.format(name=name.replace("/", "%2f"))
    try:
        payload = get_json(url)
    except Offline:
        return None
    if not payload:
        return None
    times = payload.get("time")
    if not isinstance(times, dict):
        return None
    limit = cutoff(now)
    top = parse(ceiling)
    old_enough = []
    for version, stamp in times.items():
        if version in ("created", "modified"):
            continue
        when = _parse(stamp)
        if when is None or when >= limit:
            continue
        here = parse(version)
        if top is not None and (here is None or here > top):
            continue
        old_enough.append(version)
    return newest_stable(old_enough)
