"""`go.mod` -> module requirements.

Go pins exactly by construction, so every `require` line is a pin; the only
work is stripping the `v` prefix and ignoring `// indirect` entries, which the
module graph owns rather than this repo.
"""

from __future__ import annotations

from pathlib import Path
import re

from dep_freshness._tables import GOMOD, TOOLCHAIN
from dep_freshness.models import Dep

_REQUIRE = re.compile(r"^\s*(?P<module>[^\s()]+)\s+(?P<version>v\S+)\s*(?P<rest>.*)$")


def parse(path: Path) -> list[Dep]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    deps: list[Dep] = []
    in_block = False
    for number, raw in enumerate(lines, start=1):
        line = raw.split("//")[0].strip()
        comment = raw.partition("//")[2]
        if line.startswith("go "):
            deps.append(Dep(
                ecosystem=TOOLCHAIN, name="go", constraint=line[3:].strip(),
                path=path, line=number, caret_ok=True,
            ))
            continue
        if line.startswith("require ("):
            in_block = True
            continue
        if in_block and line == ")":
            in_block = False
            continue
        if line.startswith("require "):
            line = line[len("require "):].strip()
        elif not in_block:
            continue
        match = _REQUIRE.match(line)
        if not match or "indirect" in comment:
            continue
        deps.append(Dep(
            ecosystem=GOMOD, name=match.group("module"),
            constraint=match.group("version"), path=path, line=number,
            pinned=match.group("version").lstrip("v"),
        ))
    return deps
