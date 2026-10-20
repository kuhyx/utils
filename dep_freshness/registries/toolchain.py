"""Latest stable Flutter/Dart, Node, Python and Gradle, for the toolchain checks (Q3).

Python comes from python.org's release API, NOT the interpreter running the
gate. That used to be the target, and it made the verdict a property of the
machine: `setup-python` "3.x" resolved to 3.15.0 on one runner and 3.14.8 on
another, so spellcode's `transitive:` allowlist entry was dead on one and
required on the other (2026-10-20). python.org is first-party, filters
pre-releases server-side, and answers in one request; endoflife.date is a
third party, and cpython's git tags would mean walking every rc tag.
"""

from __future__ import annotations

import re

from dep_freshness._tables import (
    FLUTTER_RELEASES,
    GRADLE_RELEASES,
    NODE_CHANNEL,
    NODE_RELEASES,
    PYTHON_RELEASES,
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


# Exactly "Python X.Y.Z": the feed also lists "Python install manager 26.4"
# (the Windows launcher), which read as a version would be Python 26.
_CPYTHON_RELEASE = re.compile(r"Python (\d+\.\d+\.\d+)")


def python_latest() -> str | None:
    """Newest final CPython release on python.org."""
    payload = get_json(PYTHON_RELEASES)
    if not payload:
        return None
    candidates = []
    for release in payload:
        match = _CPYTHON_RELEASE.fullmatch(release.get("name") or "")
        if match and not release.get("pre_release"):
            candidates.append(match.group(1))
    return newest_stable(candidates)


def gradle_latest() -> str | None:
    """Newest Gradle release, from services.gradle.org (never a nightly/RC)."""
    payload = get_json(GRADLE_RELEASES)
    if not payload:
        return None
    return newest_stable([payload.get("version")])
