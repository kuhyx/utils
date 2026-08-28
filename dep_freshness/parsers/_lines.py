"""Best-effort line numbers for keys the structured parsers give us untagged.

`yaml.safe_load` and `tomllib` both discard positions. Reporting a violation
without a line makes the fix a search, so the key is located textually after
the fact; a miss degrades to line 0 rather than failing.

Two tie-breaks, in order:

1. **Inside a declared section beats outside it.** A Flutter app declares
   `flutter_launcher_icons` twice: once as a dev dependency and once as a
   TOP-LEVEL configuration block for the same tool. Indentation alone points
   the fix at the config block, which has no version on it at all.
2. **Then least indented.** A pubspec that declares `path: ^1.9.1` as a
   dependency also has a nested `path:` inside a git block six spaces in, and
   first-match would point the fix at the wrong line.
"""

from __future__ import annotations

import re
from pathlib import Path

_KEY = re.compile(r'^(?P<indent>\s*)-?\s*["\']?(?P<key>[A-Za-z0-9_.@/-]+)["\']?\s*[:=]')


def index(path: Path, sections: tuple[str, ...] = ()) -> dict[str, int]:
    """Map `key` -> the 1-based line where it is most likely declared.

    `sections` names the top-level keys that actually hold dependencies
    (`dependencies`, `dev_dependencies`, ...). Anything found outside them is
    kept only as a fallback, so a config block sharing a package's name never
    wins over the declaration that carries the version.
    """
    best: dict[str, tuple[int, int, int]] = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    inside = not sections  # with no sections declared, everything counts
    for number, line in enumerate(text.splitlines(), start=1):
        match = _KEY.match(line)
        if not match:
            continue
        key = match.group("key")
        depth = len(match.group("indent").expandtabs(4))
        if depth == 0 and sections:
            inside = key in sections
        score = (0 if inside else 1, depth, number)
        if key not in best or score < best[key]:
            best[key] = score
    return {key: number for key, (_, _, number) in best.items()}


def find(path: Path, name: str, sections: tuple[str, ...] = ()) -> int:
    return index(path, sections).get(name, 0)
