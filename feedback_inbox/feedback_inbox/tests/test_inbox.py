# Copyright (c) 2026 Krzysztof Rudnicki
"""Import rules: complete, incomplete, idempotent, titles, due date, failures."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from feedback_inbox._entry import Report
from feedback_inbox._inbox import (
    MARKER,
    Importer,
    Outcome,
    Waiter,
    build_task,
    run_once,
    run_settled,
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


def test_complete_bundle_becomes_one_task(paths: Paths) -> None:
    bundle = make_bundle(paths.data_root)
    todo = FakeTodo()
    assert _run(paths, todo) == [Outcome.IMPORTED]
    ((repo, title, body),) = todo.calls
    assert repo == "kuhyx/cleanup-plate"
    assert (
        title
        == MANUAL + "cleanup-plate feedback: I would like to see the painting IN FULL"
    )
    assert body.startswith("Due: 2026-11-12 10:00\n\n## 2026-11-11T13:52:33")
    assert f"{bundle}/report.json" in body
    marker = json.loads((bundle / MARKER).read_text(encoding="utf-8"))
    assert marker["task_id"] == "id0001" + "0" * 28
    assert marker["due"] == "2026-11-12T10:00:00"


def test_rerun_never_duplicates(paths: Paths) -> None:
    make_bundle(paths.data_root)
    todo = FakeTodo()
    assert _run(paths, todo) == [Outcome.IMPORTED]
    assert _run(paths, todo) == [Outcome.SKIPPED]
    assert len(todo.calls) == 1


def test_incomplete_bundles_wait(paths: Paths) -> None:
    make_bundle(paths.data_root, stamp="2026-11-11T10-00-00-001", report=None)
    make_bundle(paths.data_root, stamp="2026-11-11T10-00-01-001", entry=False)
    make_bundle(paths.data_root, stamp="2026-11-11T10-00-02-001", age=0.5)
    todo = FakeTodo()
    assert _run(paths, todo) == [Outcome.PENDING] * 3
    assert todo.calls == []
    later = run_once(paths.data_root, Importer(todo, OWNER), NOW + 10)
    assert [r.outcome for r in later] == [
        Outcome.PENDING,
        Outcome.PENDING,
        Outcome.IMPORTED,
    ]


def test_multiple_games(paths: Paths) -> None:
    make_bundle(paths.data_root, game="cleanup-plate", note="a")
    make_bundle(paths.data_root, game="dread-grid", note="b")
    todo = FakeTodo()
    assert _run(paths, todo) == [Outcome.IMPORTED] * 2
    assert [(c[0], c[1]) for c in todo.calls] == [
        ("kuhyx/cleanup-plate", "MANUAL WORK REQUIRED: cleanup-plate feedback: a"),
        ("kuhyx/dread-grid", "MANUAL WORK REQUIRED: dread-grid feedback: b"),
    ]


def test_corrupt_report_still_a_task(paths: Paths) -> None:
    bundle = make_bundle(paths.data_root, report="{broken", note="keep me")
    todo = FakeTodo()
    assert _run(paths, todo) == [Outcome.IMPORTED]
    ((_, title, body),) = todo.calls
    assert (
        title
        == "MANUAL WORK REQUIRED: cleanup-plate feedback: keep me [corrupt report.json]"
    )
    assert "report.json is corrupt" in body
    assert (bundle / MARKER).exists()


def test_corrupt_report_without_note(paths: Paths) -> None:
    make_bundle(paths.data_root, report="[]", note="")
    todo = FakeTodo()
    assert _run(paths, todo) == [Outcome.IMPORTED]
    title = todo.calls[0][1]
    game_part = "museum loop=P2,carry=d,id=c 13:52"
    assert title == f"{MANUAL}cleanup-plate feedback: {game_part} [corrupt report.json]"


def test_no_note_title_names_game_combo_time(paths: Paths) -> None:
    make_bundle(paths.data_root, note="")
    todo = FakeTodo()
    assert _run(paths, todo) == [Outcome.IMPORTED]
    assert (
        todo.calls[0][1]
        == "MANUAL WORK REQUIRED: cleanup-plate feedback: museum loop=P2 13:52"
    )


def test_title_uses_first_line_and_caps_length() -> None:
    report = Report(note="\n  " + "x" * 300 + "\nsecond", game="g", combo="c")
    draft = build_task("repo", STAMP, "## e", report)
    assert draft.title == "MANUAL WORK REQUIRED: repo feedback: " + "x" * 119 + "…"
    bare = build_task("repo", STAMP, "## e", Report(note="", game="", combo=""))
    assert bare.title == "MANUAL WORK REQUIRED: repo feedback: 13:52"


def test_todo_failure_leaves_no_marker(paths: Paths) -> None:
    bundle = make_bundle(paths.data_root)
    todo = FakeTodo(fail=True)
    results = run_once(paths.data_root, Importer(todo, OWNER), NOW)
    assert [r.outcome for r in results] == [Outcome.FAILED]
    assert "todo down" in results[0].detail
    assert not (bundle / MARKER).exists()
    assert _run(paths, FakeTodo()) == [Outcome.IMPORTED]


def test_merge_is_flagged_but_marked(paths: Paths) -> None:
    make_bundle(paths.data_root)
    results = run_once(paths.data_root, Importer(FakeTodo(merged=True), OWNER), NOW)
    assert results[0].outcome is Outcome.IMPORTED
    assert "merged" in results[0].detail


def test_marker_write_failure_is_reported(paths: Paths) -> None:
    bundle = make_bundle(paths.data_root)
    (bundle / MARKER).mkdir()
    results = run_once(paths.data_root, Importer(FakeTodo(), OWNER), NOW)
    assert results[0].outcome is Outcome.SKIPPED
    (bundle / MARKER).rmdir()
    bundle.chmod(0o500)
    try:
        results = run_once(paths.data_root, Importer(FakeTodo(), OWNER), NOW)
    finally:
        bundle.chmod(0o700)
    assert results[0].outcome is Outcome.FAILED
    assert "marker" in results[0].detail


def test_run_settled_waits_then_gives_up(paths: Paths, tmp_path: Path) -> None:
    make_bundle(paths.data_root, age=0.0, now=NOW)
    clock = [NOW]
    slept: list[float] = []

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        clock[0] += seconds

    todo = FakeTodo()
    results = run_settled(
        paths.data_root, Importer(todo, OWNER), Waiter(5.0, lambda: clock[0], sleep)
    )
    assert [r.outcome for r in results] == [Outcome.IMPORTED]
    assert slept == [1.0, 1.0]

    other = tmp_path / "other"
    other.mkdir()
    make_bundle(other, report=None)
    slept.clear()
    results = run_settled(
        other, Importer(todo, OWNER), Waiter(3.0, lambda: clock[0], sleep)
    )
    assert [r.outcome for r in results] == [Outcome.PENDING]
    assert slept == [1.0, 1.0, 1.0]


def test_every_title_starts_with_the_manual_prefix(paths: Paths) -> None:
    make_bundle(paths.data_root, stamp="2026-11-11T10-00-00-001", note="a")
    make_bundle(paths.data_root, stamp="2026-11-11T10-00-01-001", note="")
    make_bundle(paths.data_root, stamp="2026-11-11T10-00-02-001", report="{")
    make_bundle(paths.data_root, game="dread-grid", note="b")
    todo = FakeTodo()
    assert _run(paths, todo) == [Outcome.IMPORTED] * 4
    titles = [call[1] for call in todo.calls]
    assert len(titles) == 4
    assert all(t.startswith("MANUAL WORK REQUIRED: ") for t in titles)
