"""Libraries consumed by git tag: `kuhyx/utils` by default, or their own repo.

"Newest" here is the newest tag matching `<package>-vX.Y.Z`, not a registry
answer. The transport is `git ls-remote` (see `_git.py`), never the REST API.

A dep pinned out of kuhyx/utils keeps its bare package name -- that is the
allowlist label and cache key every consumer already has. Any other repo is
named `<host>/<owner>/<repo>:<package>`, so the resolver (which only ever
sees the name) can still find the remote: asking utils for leisure-watch's
tags answered "undeterminable" (exit 3) in steam-backlog-enforcer.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from dep_freshness._tables import UTILS_TAG_REMOTE
from dep_freshness.registries._git import ls_remote
from dep_freshness.versions import newest_stable

_TAG = re.compile(r"refs/tags/(?P<name>[A-Za-z0-9_.-]+)-v(?P<version>[0-9][^\s]*)$")
_UTILS_SOURCE = urlsplit(UTILS_TAG_REMOTE).netloc + urlsplit(UTILS_TAG_REMOTE).path


def _source(url: str) -> str | None:
    """`host/owner/repo` behind a git URL, or None when it cannot be read."""
    parts = urlsplit(url.strip())
    path = parts.path.strip("/").removesuffix(".git")
    if not parts.hostname or path.count("/") < 1:
        return None
    return f"{parts.hostname}/{path}"


def qualified_name(url: str, package: str) -> str:
    """The dep name for `package` pinned out of `url` (see module docstring).

    An unreadable URL falls back to the bare name -- the pre-existing
    behaviour -- rather than a guessed remote.
    """
    source = _source(url)
    if source is None or source.casefold() == _UTILS_SOURCE.casefold():
        return package
    return f"{source}:{package}"


def latest(name: str) -> str | None:
    """Highest semver tag prefixed with `<package>-v`, or None if there is none."""
    source, _, package = name.rpartition(":")
    remote = f"https://{source}" if source else UTILS_TAG_REMOTE
    found = []
    for line in ls_remote(remote, "--tags", "--refs"):
        match = _TAG.search(line)
        if match and match.group("name") == package:
            found.append(match.group("version"))
    return newest_stable(found)
