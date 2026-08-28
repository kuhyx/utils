"""crates.io: `max_stable_version`, never `max_version`.

`max_version` includes pre-releases. crates.io also 403s any request without a
User-Agent, which `http.py` always sets.
"""

from __future__ import annotations

from dep_freshness._tables import CRATES_API
from dep_freshness.registries.http import get_json
from dep_freshness.versions import newest_stable


def latest(name: str) -> str | None:
    payload = get_json(CRATES_API.format(name=name))
    if not payload:
        return None
    crate = payload.get("crate") or {}
    stable = crate.get("max_stable_version")
    if stable:
        return str(stable)
    live = [
        v.get("num") for v in payload.get("versions") or [] if not v.get("yanked")
    ]
    return newest_stable(live)
