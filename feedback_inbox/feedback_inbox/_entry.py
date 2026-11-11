# Copyright (c) 2026 Krzysztof Rudnicki
"""A bundle's markdown entry and its report.json."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

_SECTION = re.compile(r"(?m)^(?=## )")
_GAME = re.compile(r"Game `([^`]*)`, combo `([^`]*)`")
_BODY_END = re.compile(r"(?m)^- Screenshot")


@dataclass(frozen=True)
class Report:
    """The fields of report.json the inbox needs."""

    note: str
    game: str
    combo: str


def find_entry(feedback_dir: Path, bundle: Path) -> str | None:
    """The ``feedback-<date>.md`` section whose paths point into ``bundle``.

    Matched by the stamp folder in its paths, not by the heading time (which
    drops the milliseconds), so a bundle never picks up a neighbour's entry.
    """
    needle = f"/{bundle.name}/"
    for md in sorted(feedback_dir.glob("feedback-*.md")):
        try:
            text = md.read_text(encoding="utf-8")
        except OSError, UnicodeDecodeError:
            continue
        for section in _SECTION.split(text):
            if needle in section:
                return section.strip()
    return None


def read_report(path: Path) -> Report | None:
    """Parse report.json; ``None`` when it cannot be read as a JSON object."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError, UnicodeDecodeError, json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return Report(
        note=_text(data.get("note")),
        game=_text(data.get("game")),
        combo=_text(data.get("combo")),
    )


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def note_from_entry(entry: str) -> str:
    """His note, as written between the heading and the file list."""
    _head, _, rest = entry.partition("\n")
    return _BODY_END.split(rest, maxsplit=1)[0].strip()


def game_and_combo(entry: str) -> tuple[str, str]:
    """Game and combo from the entry's ``Game ..., combo ...`` line."""
    found = _GAME.search(entry)
    return (found.group(1), found.group(2)) if found else ("", "")
