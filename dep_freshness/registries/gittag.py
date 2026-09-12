"""Shared libraries consumed by git tag out of `kuhyx/utils`.

"Newest" here is the newest tag matching `<package>-vX.Y.Z`, not a registry
answer. The transport is `git ls-remote` (see `_git.py`), never the REST API.
"""

from __future__ import annotations

import re

from dep_freshness._tables import UTILS_TAG_REMOTE
from dep_freshness.registries._git import ls_remote
from dep_freshness.versions import newest_stable

_TAG = re.compile(r"refs/tags/(?P<name>[A-Za-z0-9_.-]+)-v(?P<version>[0-9][^\s]*)$")


def latest(package: str, remote: str = UTILS_TAG_REMOTE) -> str | None:
    """Highest semver tag prefixed with `<package>-v`, or None if there is none."""
    found = []
    for line in ls_remote(remote, "--tags", "--refs"):
        match = _TAG.search(line)
        if match and match.group("name") == package:
            found.append(match.group("version"))
    return newest_stable(found)
