#!/usr/bin/env python3
"""Print kuhy's own submissions on one problem, failed and accepted, with code.

Usage: history.py <url-or-slug>

kuhy, 2026-11-22: a Claude coaching a problem "should also have access to my
history of approaches", including the ones that succeeded. leetcode-guard's
one-minute harvester mirrors every submission (status, time, code) into
``~/.local/share/leetcode_guard/history/<slug>.json`` (``_history_store`` in
leetcode-guard documents the shape). This reads that mirror, read-only, and
prints a bounded summary: the newest :data:`SHOWN` submissions, each code
cut at :data:`CODE_CHARS`. The mirror is display-only context and never a
gate input; nothing here writes.

Exit codes: 0 printed (also "no mirror yet" and "unreadable"), 1 bad input.

Stdlib only and free of package imports, like ``fetch_problem.py``: SKILL.md
runs it by path. Its stdout IS its interface (T201 exemption in pyproject.toml).
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import re
import sys
from typing import Final

HISTORY_DIR: Final = Path.home() / ".local" / "share" / "leetcode_guard" / "history"
SHOWN: Final = 12
"""Newest submissions printed; older ones are counted, not shown."""
CODE_CHARS: Final = 1500
"""Code longer than this is cut: one huge paste must not flood the context."""
_ARGC: Final = 2
"""argv is the script and one problem."""


def slug_from(arg: str) -> str:
    """A full problem URL or a bare slug; anything else raises ``ValueError``."""
    found = re.search(r"leetcode\.(?:com|cn)/problems/([a-z0-9-]+)", arg)
    if found:
        return found.group(1)
    if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", arg):
        return arg
    msg = f"not a LeetCode slug: {arg!r}"
    raise ValueError(msg)


def _when(raw: object) -> str:
    """Unix seconds as a UTC minute, ``?`` when off."""
    if isinstance(raw, int) and not isinstance(raw, bool):
        return datetime.fromtimestamp(raw, tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
    return "?"


def _row(item: dict[str, object]) -> str:
    """One submission: a header line and its code block."""
    stats = ", ".join(str(item.get(key, "?")) for key in ("lang", "runtime", "memory"))
    head = f"### {item.get('status', '?')} - {_when(item.get('timestamp'))} - {stats}"
    code = item.get("code")
    if not isinstance(code, str):
        return f"{head}\n(code not mirrored yet)"
    cut = "\n[cut]" if len(code) > CODE_CHARS else ""
    return f"{head}\n```\n{code[:CODE_CHARS]}{cut}\n```"


def render(arg: str) -> str:
    """The summary for one problem, as markdown."""
    slug = slug_from(arg)
    path = HISTORY_DIR / f"{slug}.json"
    if not path.exists():
        return f"No mirrored submissions for {slug} yet."
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError, ValueError:
        data = None
    rows = data.get("submissions") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return f"The submission mirror for {slug} is unreadable."
    items = [item for item in rows if isinstance(item, dict)]
    items.sort(key=lambda item: _stamp(item.get("timestamp")), reverse=True)
    accepted = sum(item.get("status") == "Accepted" for item in items)
    title = f"{len(items)} submissions ({accepted} accepted)"
    parts = [f"# kuhy's submissions on {slug}: {title}"]
    parts += [_row(item) for item in items[:SHOWN]]
    if len(items) > SHOWN:
        parts.append(f"({len(items) - SHOWN} older not shown)")
    return "\n\n".join(parts)


def _stamp(raw: object) -> int:
    """A sort key: the timestamp, 0 when off."""
    return raw if isinstance(raw, int) and not isinstance(raw, bool) else 0


def main() -> int:
    """Print the summary for the problem named on argv."""
    if len(sys.argv) != _ARGC:
        print("usage: history.py <url-or-slug>", file=sys.stderr)
        return 1
    try:
        print(render(sys.argv[1]))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
