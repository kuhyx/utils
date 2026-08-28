"""Latest stable Flutter/Dart, Node and Python, for the toolchain checks (Q3).

Python is deliberately compared against the INSTALLED interpreter rather than
python.org: on Arch it is pacman-managed, and a gate that can only be satisfied
by fighting the distro gets switched off.
"""

from __future__ import annotations

import platform

from dep_freshness._tables import (
    FLUTTER_RELEASES,
    NODE_CHANNEL,
    NODE_RELEASES,
)
from dep_freshness.registries.http import get_json
from dep_freshness.versions import newest_stable


def flutter_latest() -> tuple[str | None, str | None]:
    """`(flutter, dart)` on the stable channel."""
    payload = get_json(FLUTTER_RELEASES)
    if not payload:
        return (None, None)
    stable_hash = (payload.get("current_release") or {}).get("stable")
    for release in payload.get("releases") or []:
        if release.get("hash") == stable_hash and release.get("channel") == "stable":
            return (release.get("version"), release.get("dart_sdk_version"))
    stable = [
        r.get("version") for r in payload.get("releases") or []
        if r.get("channel") == "stable"
    ]
    return (newest_stable(stable), None)


def node_latest(channel: str = NODE_CHANNEL) -> str | None:
    """Newest Node release on the configured channel (`lts` or `current`)."""
    payload = get_json(NODE_RELEASES)
    if not payload:
        return None
    if channel == "lts":
        candidates = [r.get("version") for r in payload if r.get("lts")]
    else:
        candidates = [r.get("version") for r in payload]
    return newest_stable(candidates)


def python_installed() -> str:
    """The interpreter this gate is running under — the Python target."""
    return platform.python_version()
