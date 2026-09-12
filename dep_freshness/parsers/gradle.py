"""Gradle: `gradle/libs.versions.toml` -> Maven coordinates, and the wrapper.

The version catalog is the one place a Gradle build should declare versions,
which makes it a manifest the gate can read without evaluating Kotlin DSL.
A build may have several (`settings.gradle.kts` can `from(files(...))` any
`*.versions.toml`; TachiyomiSY has three), so the suffix is what is matched.
Three shapes appear in `[libraries]` and `[plugins]`:

    foo = "group:artifact:1.2.3"                         # inline string
    foo = { module = "group:artifact", version.ref = "x" }
    foo = { group = "g", name = "a", version = "1.2.3" }
    plug = { id = "com.example.plugin", version.ref = "x" }

A library with no version is managed by a BOM (`junit-platform-launcher`
in TachiyomiSY) and is skipped: the BOM's own entry is the pin that counts.
A rich version table (`{ strictly = "1.2" }`) is read as the constraint it
spells and lands as unpinned when it is a range, like every other ecosystem.

The line reported is the `[versions]` entry when a `version.ref` is used,
because that is where the fix goes; several libraries sharing one ref each
report the same line, which is one finding per stale artifact, not noise.

`gradle-wrapper.properties` names the Gradle distribution; that is the
toolchain pin, judged against services.gradle.org like Flutter against its
release feed.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import tomllib

from dep_freshness._tables import GITCOMMIT, JITPACK_GROUP_PREFIX, MAVEN, TOOLCHAIN
from dep_freshness.models import Dep
from dep_freshness.parsers._lines import index
from dep_freshness.versions import exact_pin

CATALOG_SUFFIX = ".versions.toml"  # libs.versions.toml, but also sy.versions.toml
WRAPPER_NAME = "gradle-wrapper.properties"
_DISTRIBUTION = re.compile(
    r"gradle-(?P<version>\d+(?:\.\d+)*(?:-[0-9A-Za-z.-]+?)?)-(?:bin|all)\.zip"
)
# JitPack accepts any commit as a version; 7 to 40 hex digits and nothing
# else is one. `1.0.0` never matches (dots), and a tag like `v2.3.0` has a
# letter outside a-f.
_COMMIT = re.compile(r"^[0-9a-f]{7,40}$")


def _commit_pin(name: str, version: str) -> bool:
    """True for `com.github.*` at a commit hash: a gitcommit dep, not maven."""
    return name.startswith(JITPACK_GROUP_PREFIX) and bool(_COMMIT.match(version))


def _rich(value: Any) -> str:
    """The version string a catalog value spells, for any of its shapes."""
    if isinstance(value, dict):
        for key in ("strictly", "require", "prefer"):
            if value.get(key):
                return str(value[key])
        return ""
    return str(value or "")


def _coordinates(entry: Any, plugin: bool) -> tuple[str, str] | None:
    """`(name, inline_version)` for a library or plugin entry, or None."""
    if isinstance(entry, str):
        parts = entry.split(":")
        if plugin:
            return (parts[0], parts[1] if len(parts) > 1 else "")
        if len(parts) < 2:
            return None
        return (f"{parts[0]}:{parts[1]}", parts[2] if len(parts) > 2 else "")
    if not isinstance(entry, dict):
        return None
    if plugin:
        name = str(entry.get("id") or "")
    elif entry.get("module"):
        name = str(entry["module"])
    else:
        name = f"{entry.get('group', '')}:{entry.get('name', '')}"
    if not name.strip(":"):
        return None
    version = entry.get("version")
    if isinstance(version, dict) and version.get("ref"):
        return (name, f"ref:{version['ref']}")
    return (name, _rich(version))


def parse_catalog(path: Path) -> list[Dep]:
    """Every versioned library and plugin in a Gradle version catalog."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return []
    versions = {k: _rich(v) for k, v in (data.get("versions") or {}).items()}
    lines = index(path)
    deps: list[Dep] = []
    for section, plugin in (("libraries", False), ("plugins", True)):
        for alias, entry in (data.get(section) or {}).items():
            coords = _coordinates(entry, plugin)
            if coords is None:
                continue
            name, version = coords
            line = lines.get(str(alias), 0)
            if version.startswith("ref:"):
                ref = version[4:]
                version = versions.get(ref, "")
                line = lines.get(ref, line)
            if not version:
                continue  # BOM-managed, or a dangling ref the build itself rejects
            if plugin:
                name = f"{name}:{name}.gradle.plugin"
            ecosystem, pinned = MAVEN, exact_pin(version)
            if _commit_pin(name, version):
                ecosystem, pinned = GITCOMMIT, version.strip()
            deps.append(
                Dep(
                    ecosystem=ecosystem,
                    name=name,
                    constraint=version,
                    path=path,
                    line=line,
                    pinned=pinned,
                )
            )
    return deps


def parse_wrapper(path: Path) -> list[Dep]:
    """The Gradle distribution the wrapper downloads, as a toolchain pin."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.startswith("distributionUrl="):
            continue
        match = _DISTRIBUTION.search(line)
        version = match.group("version") if match else ""
        return [
            Dep(
                ecosystem=TOOLCHAIN,
                name="gradle",
                constraint=version,
                path=path,
                line=number,
                pinned=exact_pin(version),
            )
        ]
    return []


def is_catalog(path: Path) -> bool:
    """True for `libs.versions.toml` and any sibling catalog a build declares."""
    return path.name.endswith(CATALOG_SUFFIX)
