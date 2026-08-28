"""PyPI: latest stable via the modern simple index.

The legacy `/pypi/<name>/json` endpoint's `info.version` includes yanked and
pre-release versions, which is exactly the fail-green bug this gate must not
have. The simple v1 JSON carries per-file `yanked` flags, so a version counts
only when at least one of its files is still installable.
"""

from __future__ import annotations

from dep_freshness._tables import PYPI_ACCEPT, PYPI_API
from dep_freshness.registries.http import get_json
from dep_freshness.versions import newest_stable

_SUFFIXES = (".tar.gz", ".zip", ".whl", ".tar.bz2", ".egg")


def _version_of(filename: str, versions: set[str]) -> str | None:
    """Which declared version a distribution filename belongs to."""
    for suffix in _SUFFIXES:
        if filename.endswith(suffix):
            filename = filename[: -len(suffix)]
            break
    parts = filename.split("-")
    for candidate in parts[1:]:
        if candidate in versions:
            return candidate
    return None


def latest(name: str) -> str | None:
    payload = get_json(PYPI_API.format(name=name), accept=PYPI_ACCEPT)
    if not payload:
        return None
    versions = [str(v) for v in payload.get("versions") or []]
    declared = set(versions)
    files = payload.get("files") or []
    if files:
        live = set()
        for entry in files:
            if entry.get("yanked"):
                continue
            found = _version_of(str(entry.get("filename", "")), declared)
            if found:
                live.add(found)
        if live:
            return newest_stable(live)
    return newest_stable(versions)
