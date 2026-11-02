"""Parse the todo server's list_tasks and get_task text replies."""

from __future__ import annotations

from dataclasses import dataclass
import re

_FIELDS = ("id", "priority", "status", "created", "updated", "repo")
_FIELDS += ("done_check", "by", "evidence")
_META_LINE = re.compile(rf"^({'|'.join(_FIELDS)}): ?(.*)$")
_MANUAL = re.compile(r"^\s*check:\s*manual\s*$", re.IGNORECASE | re.MULTILINE)
_COLUMNS = 5


def clean_title(title: str) -> str:
    """Drop surrounding space and a leading markdown ``#``."""
    return re.sub(r"^#+\s*", "", title.strip())


@dataclass(frozen=True)
class TaskLine:
    """One list_tasks row."""

    id8: str
    status: str
    priority: str
    repo: str
    title: str


@dataclass(frozen=True)
class Task:
    """One get_task reply: metadata lines, ``---``, then the note text."""

    id: str
    status: str
    repo: str | None
    done_check: str | None
    text: str

    @property
    def title(self) -> str:
        return clean_title(self.text.split("\n", 1)[0])

    @property
    def is_manual(self) -> bool:
        return _MANUAL.search(self.text) is not None


def parse_list(text: str) -> list[TaskLine]:
    """Rows of tab-separated ``id8 status priority repo title`` lines."""
    rows = []
    for raw in text.splitlines():
        parts = raw.split("\t")
        if len(parts) >= _COLUMNS:
            title = clean_title("\t".join(parts[4:]))
            rows.append(TaskLine(parts[0], parts[1], parts[2], parts[3], title))
    return rows


def parse_detail(text: str) -> Task:
    """Split a get_task reply into metadata fields and the note text."""
    meta: dict[str, str] = {}
    last = ""
    lines = text.split("\n")
    body: list[str] = []
    for index, row in enumerate(lines):
        if row == "---":
            body = lines[index + 1 :]
            break
        found = _META_LINE.match(row)
        if found:
            last = found.group(1)
            meta[last] = found.group(2)
        elif last:
            meta[last] += "\n" + row
    return Task(
        id=meta.get("id", ""),
        status=meta.get("status", ""),
        repo=meta.get("repo"),
        done_check=meta.get("done_check"),
        text="\n".join(body),
    )
