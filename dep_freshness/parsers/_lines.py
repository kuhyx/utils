"""Best-effort line numbers for keys the structured parsers give us untagged.

`yaml.safe_load` and `tomllib` both discard positions. Reporting a violation
without a line makes the fix a search, so the key is located textually after
the fact; a miss degrades to line 0 rather than failing.

Ties are broken by *indentation*, not by order: a pubspec that declares
`path: ^1.9.1` as a dependency also has a nested `path:` inside a git block six
spaces in, and first-match would point the fix at the wrong line.
"""

from __future__ import annotations

from pathlib import Path
import re

_KEY = re.compile(r'^(?P<indent>\s*)-?\s*["\']?(?P<key>[A-Za-z0-9_.@/-]+)["\']?\s*[:=]')


def index(path: Path) -> dict[str, int]:
    """Map `key` -> the 1-based line where it appears least-indented."""
    best: dict[str, tuple[int, int]] = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    for number, line in enumerate(text.splitlines(), start=1):
        match = _KEY.match(line)
        if not match:
            continue
        key = match.group("key")
        depth = len(match.group("indent").expandtabs(4))
        if key not in best or depth < best[key][0]:
            best[key] = (depth, number)
    return {key: number for key, (_, number) in best.items()}


def find(path: Path, name: str) -> int:
    return index(path).get(name, 0)
