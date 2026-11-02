"""Extract ``- title | done_check: cmd`` items from a PR's Todo section."""

from __future__ import annotations

from dataclasses import dataclass
import re

_HEADING = re.compile(r"^#{1,6}\s*todo:?\s*$", re.IGNORECASE)
_BULLET = re.compile(r"^\s*[-*]\s+(.*\S)\s*$")
_CHECK = re.compile(r"^(.*?)\s*\|\s*done_check:\s*(.*)$", re.IGNORECASE)


@dataclass(frozen=True)
class TodoItem:
    """One imported task: title and optional done_check."""

    title: str
    done_check: str | None


def parse_todo_items(body: str) -> list[TodoItem]:
    """Bullets under a ``## Todo:`` heading, up to the first non-bullet text."""
    items: list[TodoItem] = []
    inside = False
    for row in body.splitlines():
        if not inside:
            inside = bool(_HEADING.match(row))
            continue
        bullet = _BULLET.match(row)
        if bullet:
            item = _item(bullet.group(1))
            if item:
                items.append(item)
        elif row.strip():
            break
    return items


def _item(text: str) -> TodoItem | None:
    found = _CHECK.match(text)
    title, check = (found.group(1), found.group(2)) if found else (text, "")
    title = title.strip()
    return TodoItem(title, check.strip() or None) if title else None
