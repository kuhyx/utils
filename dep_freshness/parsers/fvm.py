"""`.fvmrc` -> the Flutter SDK this repo builds against.

A channel name (`"stable"`) is not a version: it tells the gate nothing to
compare, and it means two machines on the same commit can build with different
SDKs. It is therefore reported unpinned.
"""

from __future__ import annotations

import json
from pathlib import Path

from dep_freshness._tables import TOOLCHAIN
from dep_freshness.models import Dep
from dep_freshness.versions import exact_pin

CHANNELS = frozenset({"stable", "beta", "master", "main", "dev"})


def parse(path: Path) -> list[Dep]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    value = str(data.get("flutter") or "").strip()
    if not value:
        return []
    return [Dep(
        ecosystem=TOOLCHAIN, name="flutter", constraint=value, path=path,
        line=1, pinned=None if value in CHANNELS else exact_pin(value),
    )]
