"""pub.dev: latest stable of a Dart/Flutter package."""

from __future__ import annotations

from dep_freshness._tables import PUB_API
from dep_freshness.registries.http import get_json
from dep_freshness.versions import newest_stable


def latest(name: str) -> str | None:
    """Latest stable on pub.dev.

    `latest.version` is already stable-only, but the full version list is the
    safety net for packages whose only releases are pre-releases.
    """
    payload = get_json(PUB_API.format(name=name))
    if not payload:
        return None
    candidate = (payload.get("latest") or {}).get("version")
    if candidate and newest_stable([candidate]):
        return candidate
    versions = [v.get("version") for v in payload.get("versions") or []]
    return newest_stable(versions)
