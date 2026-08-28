"""`package.json` (+ lockfiles) and `.nvmrc` -> npm dependencies.

`engines.node` and `packageManager` are toolchain declarations rather than
registry packages, and are read as such. `resolutions` / `overrides` get the
same treatment as pub's `dependency_overrides`: reported, because they pin a
transitive nobody is watching.
"""

from __future__ import annotations

import json
from pathlib import Path

from dep_freshness._tables import NPM, TOOLCHAIN
from dep_freshness.models import Dep
from dep_freshness.parsers._lines import index
from dep_freshness.versions import exact_pin

# (section, is_dev, is_override, is_peer)
_SECTIONS = (
    ("dependencies", False, False, False),
    ("devDependencies", True, False, False),
    ("optionalDependencies", False, False, False),
    ("peerDependencies", False, False, True),
    ("resolutions", False, True, False),
    ("overrides", False, True, False),
)
_LOCAL_PREFIXES = ("file:", "link:", "workspace:", "git+", "github:", "npm:")


def _load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def parse_package_json(path: Path) -> list[Dep]:
    data = _load(path)
    if not data:
        return []
    lines = index(path)
    deps: list[Dep] = []

    node = (data.get("engines") or {}).get("node")
    if isinstance(node, str):
        deps.append(Dep(
            ecosystem=TOOLCHAIN, name="node", constraint=node, path=path,
            line=lines.get("node", 0), pinned=exact_pin(node), caret_ok=True,
        ))

    # `packageManager: pnpm@10.13.1` is an exact pin of the package manager
    # itself, which corepack enforces -- a real dependency, and the only one
    # three of these repos omit entirely.
    manager = data.get("packageManager")
    if isinstance(manager, str) and "@" in manager:
        name, _, version = manager.rpartition("@")
        deps.append(Dep(
            ecosystem=NPM, name=name, constraint=version, path=path,
            line=lines.get("packageManager", 0), pinned=exact_pin(version),
            dev=True,
        ))

    for section, is_dev, is_override, is_peer in _SECTIONS:
        for name, spec in (data.get(section) or {}).items():
            if not isinstance(spec, str) or spec.startswith(_LOCAL_PREFIXES):
                continue
            deps.append(Dep(
                ecosystem=NPM, name=str(name), constraint=spec, path=path,
                line=lines.get(str(name), 0), pinned=exact_pin(spec),
                dev=is_dev, override=is_override, peer=is_peer,
            ))
    return deps


def parse_nvmrc(path: Path) -> list[Dep]:
    try:
        value = path.read_text(encoding="utf-8").strip().splitlines()[0].strip()
    except (OSError, IndexError):
        return []
    return [Dep(
        ecosystem=TOOLCHAIN, name="node", constraint=value, path=path,
        line=1, pinned=exact_pin(value),
    )]
