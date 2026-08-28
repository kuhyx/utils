"""npm: latest stable, refusing a pre-release published to `dist-tags.latest`.

npm lets a maintainer point `latest` at `3.0.0-rc.1`. Trusting it reports the
repo as current while it sits on an older stable, so the tag is only accepted
after it survives the pre-release check.
"""

from __future__ import annotations

from dep_freshness._tables import NPM_ACCEPT, NPM_API
from dep_freshness.registries.http import get_json
from dep_freshness.versions import is_prerelease, newest_stable


def latest(name: str) -> str | None:
    url = NPM_API.format(name=name.replace("/", "%2f"))
    payload = get_json(url, accept=NPM_ACCEPT)
    if not payload:
        return None
    tag = (payload.get("dist-tags") or {}).get("latest")
    if tag and not is_prerelease(str(tag)):
        return str(tag)
    return newest_stable((payload.get("versions") or {}).keys())
