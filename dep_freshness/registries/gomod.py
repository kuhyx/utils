"""Go module proxy: latest stable, rejecting `+incompatible` and pre-releases."""

from __future__ import annotations

from dep_freshness._tables import GOPROXY_API
from dep_freshness.registries.http import get_json
from dep_freshness.versions import is_prerelease


def latest(module: str) -> str | None:
    payload = get_json(GOPROXY_API.format(name=module.lower()))
    if not payload:
        return None
    version = str(payload.get("Version") or "")
    if not version or "+incompatible" in version or is_prerelease(version):
        return None
    return version.lstrip("v")
