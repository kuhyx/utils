"""Drill folders: ``meta.json``, ``DOCS-task.md``, ``schema.sql``, ``expected.txt``."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import TYPE_CHECKING

from sql_drills import _paths
from sql_drills._model import (
    TOPICS,
    Drill,
    DrillMeta,
    Table,
    UnknownDrillError,
)
from sql_drills._normalize import Rows, parse_rows

if TYPE_CHECKING:
    from pathlib import Path

    from sql_drills._model import Source

PREVIEW_ROWS = 5


def topics() -> list[str]:
    return list(TOPICS)


@dataclass(frozen=True)
class Record:
    meta: DrillMeta
    folder: Path
    error_code: int | None
    error_message: str | None

    def text(self, name: str) -> str:
        return (self.folder / name).read_text()

    def expected_rows(self) -> Rows:
        return parse_rows(self.text("expected.txt"))


def _record(folder: Path, source: Source) -> Record:
    info = json.loads((folder / "meta.json").read_text())
    title = (folder / "DOCS-task.md").read_text().splitlines()[0].lstrip("# ")
    meta = DrillMeta(folder.name, title, info["topic"], info["kind"], source)
    return Record(meta, folder, info.get("error_code"), info.get("error_message"))


def _scan(root: Path, source: Source) -> list[Record]:
    if not root.is_dir():
        return []
    return [
        _record(folder, source)
        for folder in sorted(root.iterdir())
        if (folder / "meta.json").is_file()
    ]


def records() -> list[Record]:
    return _scan(_paths.builtin_dir(), "builtin") + _scan(
        _paths.generated_dir(), "generated"
    )


def find(key: str) -> Record:
    found = records()
    for rec in found:
        if rec.meta.id == key:
            return rec
    for rec in found:
        if rec.meta.source == "builtin" and rec.meta.id.split("_", 1)[0] == key:
            return rec
    msg = f"unknown drill: {key}"
    raise UnknownDrillError(msg)


def list_drills() -> list[DrillMeta]:
    return [rec.meta for rec in records()]


def get_drill(key: str) -> Drill:
    rec = find(key)
    raw = json.loads(rec.text("tables.json"))
    tables = {name: Table(t["columns"], t["rows"]) for name, t in raw.items()}
    predict = rec.meta.kind == "predict"
    return Drill(
        meta=rec.meta,
        task_md=rec.text("DOCS-task.md"),
        schema_sql=rec.text("schema.sql"),
        tables=tables,
        expected_preview=[] if predict else rec.expected_rows()[:PREVIEW_ROWS],
        query=rec.text("query.sql").strip() if predict else None,
    )
