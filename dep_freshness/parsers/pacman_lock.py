"""A pacman-repo lock -> one package pinned out of an Arch-style repo db.

The format is one `key=value` per line, `#` comments allowed:

    name=proton-cachyos-native
    repo=https://mirror.cachyos.org/repo/x86_64/cachyos/cachyos.db
    version=1:11.0.20261015-1
    sha256=<hex>

There is no fixed filename, so `is_lock` recognises one by content: a
`*.lock` file whose first few KB hold a `repo=` line ending in `.db`. That
keeps Cargo.lock, pubspec.lock and friends out without a name list, and lets
pre-commit pass the file by name. `version` is kept verbatim: the epoch makes
it unreadable to `exact_pin`, and the judge compares it with pacman's vercmp.
`sha256` rides in `Dep.locked`, the field for "what the lock resolved to".
"""

from __future__ import annotations

import re
from pathlib import Path

from dep_freshness._tables import (
    PACMAN_LOCK_SNIFF_BYTES,
    PACMAN_LOCK_SUFFIX,
    PACMAN_REPO,
)
from dep_freshness.models import Dep
from dep_freshness.registries.pacman_repo import qualified_name

_REPO_DB = re.compile(r"^\s*repo\s*=\s*\S+\.db\s*$", re.MULTILINE)


def is_lock(path: Path) -> bool:
    """True for a `*.lock` whose head names a repo `.db`."""
    if not path.name.endswith(PACMAN_LOCK_SUFFIX):
        return False
    try:
        with path.open("rb") as handle:
            head = handle.read(PACMAN_LOCK_SNIFF_BYTES)
    except OSError:
        return False
    return bool(_REPO_DB.search(head.decode("utf-8", errors="replace")))


def _fields(text: str) -> dict[str, tuple[str, int]]:
    """`key -> (value, 1-based line)`; the first occurrence of a key wins."""
    fields: dict[str, tuple[str, int]] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        fields.setdefault(key.strip(), (value.strip(), number))
    return fields


def parse(path: Path) -> list[Dep]:
    if not is_lock(path):
        return []
    try:
        fields = _fields(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return []
    name, name_line = fields.get("name", ("", 0))
    repo, _ = fields.get("repo", ("", 0))
    if not name or not repo:
        return []
    version, version_line = fields.get("version", ("", 0))
    sha, _ = fields.get("sha256", ("", 0))
    return [
        Dep(
            ecosystem=PACMAN_REPO,
            name=qualified_name(repo, name),
            constraint=version,
            path=path,
            line=version_line or name_line,
            pinned=version or None,
            locked=sha.lower() or None,
        )
    ]
