"""`pubspec.yaml` (+ `pubspec.lock`) -> Dart/Flutter dependencies.

Three shapes live in the same map: a plain constraint (`http: ^1.6.0`), an SDK
package (`flutter: {sdk: flutter}`) and a git-tag dependency on `kuhyx/utils`,
whose "latest" is a tag rather than a registry version. `dependency_overrides`
is parsed too and always reported: an override is an unpinned dependency
wearing a disguise.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from dep_freshness._tables import (
    GITTAG,
    PUB,
    PUB_CARET_ALLOWED,
    PUB_OVERRIDE_KEY,
    PUB_SDK_PACKAGES,
    TOOLCHAIN,
)
from dep_freshness.models import Dep
from dep_freshness.parsers._lines import index
from dep_freshness.versions import exact_pin

_SECTIONS = (("dependencies", False), ("dev_dependencies", True))


def _load(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def locked_versions(lock: Path) -> dict[str, str]:
    """`package -> resolved version` from a committed `pubspec.lock`.

    A missing lock means "library, check the manifest alone" (four of the nine
    shared libs gitignore theirs) — never a violation.
    """
    data = _load(lock)
    out: dict[str, str] = {}
    for name, entry in (data.get("packages") or {}).items():
        if isinstance(entry, dict) and entry.get("version"):
            out[str(name)] = str(entry["version"])
    return out


def _git_ref(spec: dict) -> str | None:
    git = spec.get("git")
    if isinstance(git, dict):
        return str(git.get("ref") or "") or None
    return None


def parse(path: Path) -> list[Dep]:
    data = _load(path)
    if not data:
        return []
    lines = index(path)
    locks = locked_versions(path.with_name("pubspec.lock"))
    deps: list[Dep] = []

    sdk = ((data.get("environment") or {}) or {}).get("sdk")
    if isinstance(sdk, str):
        deps.append(Dep(
            ecosystem=TOOLCHAIN, name="dart", constraint=sdk, path=path,
            line=lines.get("sdk", 0), pinned=exact_pin(sdk), caret_ok=True,
        ))

    sections = [*_SECTIONS, (PUB_OVERRIDE_KEY, False)]
    for section, is_dev in sections:
        for name, spec in (data.get(section) or {}).items():
            name = str(name)
            override = section == PUB_OVERRIDE_KEY
            if isinstance(spec, dict) and (ref := _git_ref(spec)):
                package, _, version = ref.rpartition("-v")
                deps.append(Dep(
                    ecosystem=GITTAG, name=package or name, constraint=ref,
                    path=path, line=lines.get(name, 0), pinned=version or None,
                    dev=is_dev, override=override,
                ))
                continue
            if name in PUB_SDK_PACKAGES or (
                isinstance(spec, dict) and "sdk" in spec
            ):
                continue  # ships with the SDK; no registry version exists
            if isinstance(spec, dict):
                continue  # path/hosted dep: nothing comparable to a registry
            constraint = "" if spec is None else str(spec)
            deps.append(Dep(
                ecosystem=PUB, name=name, constraint=constraint, path=path,
                line=lines.get(name, 0), pinned=exact_pin(constraint),
                locked=locks.get(name), dev=is_dev,
                caret_ok=name in PUB_CARET_ALLOWED, override=override,
            ))
    return deps
