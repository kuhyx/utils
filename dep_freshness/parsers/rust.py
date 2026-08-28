"""`Cargo.toml` -> crates.io dependencies.

A dependency is either a bare string (`serde = "1.0.229"`) or a table with a
`version` key; path and git dependencies have no registry version and are
skipped. Cargo's bare `"1.0"` is a caret range, so only a full three-part
version counts as pinned — `"1.0"` is reported unpinned, which is correct.
"""

from __future__ import annotations

from pathlib import Path
import tomllib

from dep_freshness._tables import CARGO
from dep_freshness.models import Dep
from dep_freshness.parsers._lines import index
from dep_freshness.versions import exact_pin

_SECTIONS = (
    ("dependencies", False),
    ("dev-dependencies", True),
    ("build-dependencies", True),
)


def parse(path: Path) -> list[Dep]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return []
    lines = index(path)
    deps: list[Dep] = []
    for section, is_dev in _SECTIONS:
        for name, spec in (data.get(section) or {}).items():
            if isinstance(spec, dict):
                if "path" in spec or "git" in spec:
                    continue
                constraint = str(spec.get("version") or "")
            else:
                constraint = str(spec)
            if not constraint:
                continue
            pinned = exact_pin(constraint)
            if pinned and pinned.count(".") < 2:
                pinned = None  # "1.0" is a caret range in Cargo, not a pin
            deps.append(Dep(
                ecosystem=CARGO, name=str(name), constraint=constraint,
                path=path, line=lines.get(str(name), 0), pinned=pinned,
                dev=is_dev,
            ))
    return deps
