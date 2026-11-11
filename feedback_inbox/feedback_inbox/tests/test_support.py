# Copyright (c) 2026 Krzysztof Rudnicki
"""Builders for fake feedback bundles and a fake todo client."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from typing import TYPE_CHECKING

from feedback_inbox._todo import TaskRef, TodoError

if TYPE_CHECKING:
    from pathlib import Path

STAMP = "2026-11-11T13-52-33-162"
NOTE = "I would like to see the painting IN FULL\n\nsecond paragraph"


def entry_text(bundle: Path, note: str = NOTE, game: str = "museum") -> str:
    """The markdown entry a game appends for ``bundle``."""
    head = note.splitlines()[0][:70] if note else ""
    parts = [f"## 2026-11-11T13:52:33: {head}", ""]
    if note:
        parts += [note, ""]
    parts += [
        f"- Screenshot: `{bundle}/annotated.png`",
        f"- Report: `{bundle}/report.json`",
        f"- Game `{game}`, combo `loop=P2,carry=d,id=c`, build abc, session `s`",
        "",
        "Task: Read the annotated screenshot and fix it.",
        "",
    ]
    return "\n".join(parts)


def make_bundle(
    data_root: Path,
    *,
    game: str = "cleanup-plate",
    stamp: str = STAMP,
    note: str = NOTE,
    report: str | None = "ok",
    entry: bool = True,
    age: float = 60.0,
    now: float = 1_000_000.0,
) -> Path:
    """Create ``<game>_binaries/feedback/<stamp>/`` and its md entry."""
    feedback = data_root / f"{game}_binaries" / "feedback"
    bundle = feedback / stamp
    bundle.mkdir(parents=True, exist_ok=True)
    if report is not None:
        path = bundle / "report.json"
        if report == "ok":
            body = json.dumps({"note": note, "game": "museum", "combo": "loop=P2"})
        else:
            body = report
        path.write_text(body, encoding="utf-8")
        os.utime(path, (now - age, now - age))
    if entry:
        md = feedback / f"feedback-{stamp[:10]}.md"
        with md.open("a", encoding="utf-8") as handle:
            handle.write(entry_text(bundle, note))
    return bundle


@dataclass
class FakeTodo:
    """A todo server stand-in that stores notes the way the real one does."""

    calls: list[tuple[str, str, str]] = field(default_factory=list)
    stored: dict[str, str] = field(default_factory=dict)
    fail: bool = False
    fail_update: bool = False
    merged: bool = False
    updated: list[str] = field(default_factory=list)

    def add_task(self, repo: str, title: str, body: str) -> TaskRef:
        if self.fail:
            msg = "todo down"
            raise TodoError(msg)
        self.calls.append((repo, title, body))
        task_id = f"id{len(self.calls):04d}" + "0" * 28
        # A new_note task: title "<name> todos: <title>", then a "## <title>"
        # section holding the body.
        name = repo.rsplit("/", maxsplit=1)[-1]
        self.stored[task_id] = f"{name} todos: {title}\n\n## {title}\n{body}"
        return TaskRef(task_id=task_id, merged=self.merged)

    def update_task(self, task_id: str, title: str, body: str) -> None:
        if self.fail_update:
            msg = "update refused"
            raise TodoError(msg)
        self.updated.append(task_id)
        self.stored[task_id] = f"{title}\n\n{body}"
