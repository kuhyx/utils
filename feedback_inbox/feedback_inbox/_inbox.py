# Copyright (c) 2026 Krzysztof Rudnicki
"""Turn complete feedback bundles into todo tasks, once each."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import json
import logging
import re
from typing import TYPE_CHECKING

from feedback_inbox._bundle import (
    bundles_in,
    due_at,
    feedback_dirs,
    parse_stamp,
    repo_name,
)
from feedback_inbox._entry import (
    Report,
    find_entry,
    game_and_combo,
    note_from_entry,
    read_report,
)
from feedback_inbox._todo import TodoError

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from feedback_inbox._todo import TodoClient

LOG = logging.getLogger("feedback_inbox")
MARKER = ".inbox-imported.json"
# Marker format 2: the stored note was rewritten to our exact title and body.
FORMAT = 2
SETTLE_SECONDS = 2.0
TITLE_CAP = 120
MANUAL_PREFIX = "MANUAL WORK REQUIRED: "
CORRUPT_TAG = " [corrupt report.json]"
CORRUPT_LINE = "Warning: report.json is corrupt; the note below comes from the entry."


class Outcome(StrEnum):
    """What happened to one bundle in a run."""

    IMPORTED = "imported"
    SKIPPED = "skipped"
    PENDING = "pending"
    FAILED = "failed"


@dataclass(frozen=True)
class Result:
    """One bundle's outcome, for the journal and the exit code."""

    bundle: Path
    outcome: Outcome
    task_id: str | None = None
    detail: str = ""


@dataclass(frozen=True)
class TaskDraft:
    """The task to create: title, body and due time."""

    title: str
    body: str
    due: str


def _demote(entry: str) -> str:
    """Turn ``## `` headings into ``### ``: no section may start a todo part.

    The todo app splits a note into runnable parts at every ``## `` heading,
    so the entry's own headings must not look like sections.
    """
    return re.sub(r"(?m)^##(?=\s)", "###", entry)


def _first_line(note: str, fallback: str) -> str:
    first = next((x.strip() for x in note.splitlines() if x.strip()), "")
    if len(first) > TITLE_CAP:
        first = first[: TITLE_CAP - 1] + "…"
    return first or fallback


def build_task(repo: str, stamp: str, entry: str, report: Report | None) -> TaskDraft:
    """Compose the title and body from the entry and (maybe corrupt) report."""
    found_game, found_combo = game_and_combo(entry)
    note = note_from_entry(entry) if report is None else report.note
    game = (report.game if report else "") or found_game
    combo = (report.combo if report else "") or found_combo
    clock = parse_stamp(stamp).strftime("%H:%M")
    fallback = " ".join(x for x in (game, combo, clock) if x)
    suffix = CORRUPT_TAG if report is None else ""
    title = f"{MANUAL_PREFIX}{repo} feedback: {_first_line(note, fallback)}{suffix}"
    due = due_at(stamp)
    lines = [f"Due: {due:%Y-%m-%d %H:%M}", ""]
    if report is None:
        lines += [CORRUPT_LINE, ""]
    return TaskDraft(title, "\n".join([*lines, _demote(entry)]), due.isoformat())


def _write_marker(bundle: Path, payload: dict[str, object]) -> None:
    tmp = bundle / f"{MARKER}.tmp"
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(bundle / MARKER)


def _read_marker(bundle: Path) -> dict[str, object] | None:
    """The bundle's marker, or None when it is not a usable marker."""
    try:
        data = json.loads((bundle / MARKER).read_text(encoding="utf-8"))
    except OSError, UnicodeDecodeError, json.JSONDecodeError:
        return None
    ok = isinstance(data, dict) and isinstance(data.get("task_id"), str)
    return data if ok and isinstance(data.get("title"), str) else None


@dataclass(frozen=True)
class Importer:
    """Who files the tasks (``client``) under which GitHub owner."""

    client: TodoClient
    owner: str
    settle: float = SETTLE_SECONDS

    def import_bundle(self, feedback_dir: Path, bundle: Path, now: float) -> Result:
        """Import one bundle if complete; repair the title of one already filed."""
        if (bundle / MARKER).exists():
            return self._repair(feedback_dir, bundle)
        report_path = bundle / "report.json"
        entry = find_entry(feedback_dir, bundle)
        if entry is None or not report_path.is_file():
            return Result(bundle, Outcome.PENDING, detail="report or entry missing")
        if now - report_path.stat().st_mtime < self.settle:
            return Result(bundle, Outcome.PENDING, detail="report.json settling")
        repo = repo_name(feedback_dir)
        draft = build_task(repo, bundle.name, entry, read_report(report_path))
        return self._file(bundle, f"{self.owner}/{repo}", draft)

    def _file(self, bundle: Path, repo: str, draft: TaskDraft) -> Result:
        """Create the task, write the marker, then fix the title."""
        try:
            ref = self.client.add_task(repo, draft.title, draft.body)
        except TodoError as exc:
            return Result(bundle, Outcome.FAILED, detail=str(exc))
        # Marker first: once the task exists a retry must never add a second.
        # A merged task belongs to another note, which is not ours to rewrite.
        payload: dict[str, object] = {
            "task_id": ref.task_id,
            "title": draft.title,
            "due": draft.due,
            "merged": ref.merged,
        }
        if ref.merged:
            payload["format"] = FORMAT
        try:
            _write_marker(bundle, payload)
        except OSError as exc:
            return Result(
                bundle,
                Outcome.FAILED,
                ref.task_id,
                f"task {ref.task_id} filed but marker not written: {exc}",
            )
        if ref.merged:
            return Result(
                bundle, Outcome.IMPORTED, ref.task_id, "merged into an existing note"
            )
        return self._finish(bundle, payload, draft)

    def _repair(self, feedback_dir: Path, bundle: Path) -> Result:
        """Finish a filed task whose rewrite never completed (or predates it)."""
        data = _read_marker(bundle)
        if data is None or data.get("merged") or data.get("format") == FORMAT:
            return Result(bundle, Outcome.SKIPPED)
        entry = find_entry(feedback_dir, bundle)
        if entry is None:
            return Result(bundle, Outcome.PENDING, detail="entry missing for repair")
        report = read_report(bundle / "report.json")
        draft = build_task(repo_name(feedback_dir), bundle.name, entry, report)
        return self._finish(bundle, data, draft)

    def _finish(
        self, bundle: Path, data: dict[str, object], draft: TaskDraft
    ) -> Result:
        """Rewrite the stored note to the exact title/body, then mark it done."""
        task_id = str(data["task_id"])
        try:
            self.client.update_task(task_id, draft.title, draft.body)
        except TodoError as exc:
            return Result(bundle, Outcome.FAILED, task_id, f"update: {exc}")
        marked = {**data, "title": draft.title, "due": draft.due, "format": FORMAT}
        try:
            _write_marker(bundle, marked)
        except OSError as exc:
            return Result(bundle, Outcome.FAILED, task_id, f"marker not written: {exc}")
        return Result(bundle, Outcome.IMPORTED, task_id)


@dataclass(frozen=True)
class Waiter:
    """How long to wait for half-written bundles, and the clock to do it by."""

    wait: float
    clock: Callable[[], float]
    sleep: Callable[[float], None]


def run_once(data_root: Path, importer: Importer, now: float) -> list[Result]:
    """Import every complete, not yet imported bundle of every game."""
    return [
        importer.import_bundle(folder, bundle, now)
        for folder in feedback_dirs(data_root)
        for bundle in bundles_in(folder)
    ]


def run_settled(data_root: Path, importer: Importer, waiter: Waiter) -> list[Result]:
    """Like :func:`run_once`, retrying up to ``wait`` s while bundles are pending.

    A bundle is written in pieces; the watch fires on the first piece, so a
    short wait lets the rest land instead of leaving it to the timer.
    """
    deadline = waiter.clock() + waiter.wait
    while True:
        results = run_once(data_root, importer, waiter.clock())
        pending = any(r.outcome is Outcome.PENDING for r in results)
        if not pending or waiter.clock() >= deadline:
            return results
        waiter.sleep(1.0)
