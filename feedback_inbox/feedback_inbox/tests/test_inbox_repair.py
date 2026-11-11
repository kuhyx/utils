# Copyright (c) 2026 Krzysztof Rudnicki
"""Exact titles, section-free bodies, and repair of half-finished tasks."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from feedback_inbox._entry import Report
from feedback_inbox._inbox import (
    FORMAT,
    MARKER,
    Importer,
    Outcome,
    build_task,
    run_once,
)
from feedback_inbox.tests.test_support import STAMP, FakeTodo, make_bundle

if TYPE_CHECKING:
    from pathlib import Path

    from feedback_inbox._paths import Paths

NOW = 1_000_000.0
OWNER = "kuhyx"
MANUAL = "MANUAL WORK REQUIRED: "


def _run(paths: Paths, todo: FakeTodo) -> list[Outcome]:
    return [r.outcome for r in run_once(paths.data_root, Importer(todo, OWNER), NOW)]


def _marker(bundle: Path) -> dict[str, object]:
    data: dict[str, object] = json.loads((bundle / MARKER).read_text(encoding="utf-8"))
    return data


def _no_extra_sections(text: str) -> bool:
    return not any(line.startswith("## ") for line in text.splitlines())


def test_stored_note_is_one_manual_part(paths: Paths) -> None:
    bundle = make_bundle(paths.data_root)
    todo = FakeTodo()
    assert _run(paths, todo) == [Outcome.IMPORTED]
    (stored,) = todo.stored.values()
    assert stored.startswith(MANUAL)
    assert _no_extra_sections(stored)
    assert "### 2026-11-11T13:52:33" in stored
    assert _marker(bundle)["format"] == FORMAT


def test_entry_headings_never_become_sections() -> None:
    entry = "## a heading\ntext\n## another\n### kept"
    draft = build_task("r", STAMP, entry, Report(note="n", game="", combo=""))
    assert _no_extra_sections(draft.body)
    assert "### a heading\ntext\n### another\n### kept" in draft.body


def test_failed_update_keeps_marker_and_retries_without_a_second_task(
    paths: Paths,
) -> None:
    bundle = make_bundle(paths.data_root)
    todo = FakeTodo(fail_update=True)
    results = run_once(paths.data_root, Importer(todo, OWNER), NOW)
    assert [r.outcome for r in results] == [Outcome.FAILED]
    assert "update refused" in results[0].detail
    assert "format" not in _marker(bundle)
    todo.fail_update = False
    assert _run(paths, todo) == [Outcome.IMPORTED]
    assert len(todo.calls) == 1
    (stored,) = todo.stored.values()
    assert stored.startswith(MANUAL)
    assert _no_extra_sections(stored)
    assert _run(paths, todo) == [Outcome.SKIPPED]


def test_old_marker_is_repaired_from_the_bundle(paths: Paths) -> None:
    bundle = make_bundle(paths.data_root)
    task_id = "abc" + "0" * 33
    (bundle / MARKER).write_text(
        json.dumps({"task_id": task_id, "title": "old", "title_fixed": True}),
        encoding="utf-8",
    )
    todo = FakeTodo()
    assert _run(paths, todo) == [Outcome.IMPORTED]
    assert todo.calls == []
    assert todo.stored[task_id].startswith(MANUAL)
    assert _no_extra_sections(todo.stored[task_id])
    assert _marker(bundle)["format"] == FORMAT


def test_old_marker_whose_entry_vanished_waits(paths: Paths) -> None:
    bundle = make_bundle(paths.data_root, entry=False)
    (bundle / MARKER).write_text(
        json.dumps({"task_id": "t" * 36, "title": "old"}), encoding="utf-8"
    )
    todo = FakeTodo()
    assert _run(paths, todo) == [Outcome.PENDING]
    assert todo.updated == []


def test_merged_task_is_not_rewritten(paths: Paths) -> None:
    bundle = make_bundle(paths.data_root)
    todo = FakeTodo(merged=True)
    assert _run(paths, todo) == [Outcome.IMPORTED]
    assert todo.updated == []
    assert _marker(bundle)["format"] == FORMAT
    assert _run(paths, todo) == [Outcome.SKIPPED]


def test_old_merged_marker_is_left_alone(paths: Paths) -> None:
    bundle = make_bundle(paths.data_root)
    (bundle / MARKER).write_text(
        json.dumps({"task_id": "t" * 36, "title": "x", "merged": True}),
        encoding="utf-8",
    )
    todo = FakeTodo()
    assert _run(paths, todo) == [Outcome.SKIPPED]
    assert todo.updated == []


def test_unreadable_marker_is_left_alone(paths: Paths) -> None:
    bundle = make_bundle(paths.data_root)
    for junk in ("{broken", "[1]", '{"task_id": 5}'):
        (bundle / MARKER).write_text(junk, encoding="utf-8")
        todo = FakeTodo()
        assert _run(paths, todo) == [Outcome.SKIPPED]
        assert todo.calls == []
        assert todo.updated == []


def test_repair_reports_an_unwritable_marker(paths: Paths) -> None:
    bundle = make_bundle(paths.data_root)
    (bundle / MARKER).write_text(
        json.dumps({"task_id": "t" * 36, "title": "T"}), encoding="utf-8"
    )
    bundle.chmod(0o500)
    try:
        results = run_once(paths.data_root, Importer(FakeTodo(), OWNER), NOW)
    finally:
        bundle.chmod(0o700)
    assert results[0].outcome is Outcome.FAILED
    assert "marker not written" in results[0].detail
