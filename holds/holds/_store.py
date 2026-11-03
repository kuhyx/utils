# Copyright (c) 2026 Krzysztof Rudnicki
"""Read and write the hold file. The path is resolved on every call."""

from __future__ import annotations

import json
import os
from pathlib import Path

from holds._model import Hold, HoldsError

_ENV = "HOLDS_DATA"


def data_path() -> Path:
    """``$HOLDS_DATA`` or ``~/.local/share/holds/holds.json``."""
    override = os.environ.get(_ENV)
    if override:
        return Path(override)
    return Path.home() / ".local" / "share" / "holds" / "holds.json"


def load() -> list[Hold]:
    """All holds; a missing file is empty, anything unreadable raises."""
    path = data_path()
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except OSError as exc:
        msg = f"hold file unreadable: {path}: {exc}"
        raise HoldsError(msg) from exc
    try:
        rows = json.loads(raw)["holds"]
    except (KeyError, TypeError, ValueError) as exc:
        msg = f"hold file unreadable: {path}: {exc!r}"
        raise HoldsError(msg) from exc
    if not isinstance(rows, list):
        msg = f"hold file unreadable: {path}: 'holds' is not a list"
        raise HoldsError(msg)
    try:
        return [Hold.from_row(row) for row in rows]
    except (KeyError, TypeError, ValueError) as exc:
        msg = f"hold file unreadable: {path}: {exc!r}"
        raise HoldsError(msg) from exc


def save(items: list[Hold]) -> None:
    """Atomically replace the file with ``items`` sorted by start."""
    path = data_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [h.to_row() for h in sorted(items, key=lambda h: h.start)]
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"holds": rows}, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
