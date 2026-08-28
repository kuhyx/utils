"""Shared libraries consumed by git tag out of `kuhyx/utils`.

"Newest" here is the newest tag matching `<package>-vX.Y.Z`, not a registry
answer. Deliberately `git ls-remote` rather than the GitHub REST API: that API
allows 60 unauthenticated requests an hour, which ~20 consuming manifests would
exhaust on a single `--all` run.
"""

from __future__ import annotations

import re
import subprocess

from dep_freshness._tables import UTILS_TAG_REMOTE
from dep_freshness.registries.http import Offline, host_reachable
from dep_freshness.versions import newest_stable

_TAG = re.compile(r"refs/tags/(?P<name>[A-Za-z0-9_.-]+)-v(?P<version>[0-9][^\s]*)$")


def latest(package: str, remote: str = UTILS_TAG_REMOTE) -> str | None:
    """Highest semver tag prefixed with `<package>-v`, or None if there is none."""
    if not host_reachable(remote):
        raise Offline(remote)
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--tags", "--refs", remote],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise Offline(f"{remote}: {exc}") from exc
    if result.returncode != 0:
        raise Offline(f"{remote}: git ls-remote exit {result.returncode}")
    found = []
    for line in result.stdout.splitlines():
        match = _TAG.search(line.strip())
        if match and match.group("name") == package:
            found.append(match.group("version"))
    return newest_stable(found)
