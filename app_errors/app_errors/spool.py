# Copyright (c) 2026 Krzysztof Rudnicki
"""The local spool: how PC apps (Tk gate windows, Godot games) report.

They run on the PC the ingest runs on, so they need no RTDB: each report is
one JSON line appended to ``<spool>/<app>.jsonl`` (the writers are
``gatelock.error_report`` and the Godot ``app_errors`` addon; this module is
the reference writer and the reader). The ingest claims a file by renaming it
to ``.jsonl.ingesting`` before reading, so a line appended meanwhile lands in
a fresh file and is never lost. The spool sits beside, not inside, the
board's ``app-errors/`` folder, which reads every ``*.json`` there.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import TYPE_CHECKING

from app_errors.store import APP_NAME

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping
    from pathlib import Path

SUFFIX = ".jsonl"
CLAIMED = ".jsonl.ingesting"


@dataclass(frozen=True)
class Line:
    """One spooled report: its app, a stable id and the decoded entry."""

    app: str
    id: str
    entry: object


def append(folder: Path, app: str, entry: Mapping[str, object]) -> None:
    """Append ``entry`` as one line to ``app``'s spool file."""
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / f"{app}{SUFFIX}").open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def _claim(folder: Path) -> list[Path]:
    for path in folder.glob(f"*{SUFFIX}"):
        path.replace(path.with_name(path.name.removesuffix(SUFFIX) + CLAIMED))
    return sorted(folder.glob(f"*{CLAIMED}"))


def drain(folder: Path) -> Iterator[Line]:
    """Yield every spooled line, then delete the files it came from."""
    if not folder.is_dir():
        return
    for path in _claim(folder):
        app = path.name.removesuffix(CLAIMED)
        if APP_NAME.match(app):
            for text in path.read_text(encoding="utf-8").splitlines():
                try:
                    entry = json.loads(text)
                except ValueError:
                    continue
                digest = hashlib.sha1(text.encode()).hexdigest()[:20]  # noqa: S324 -- an id, not security
                yield Line(app, f"spool/{digest}", entry)
        path.unlink()
