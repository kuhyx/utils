# Copyright (c) 2026 Krzysztof Rudnicki
"""Discovery, stamps and due dates."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from feedback_inbox._bundle import bundles_in, due_at, feedback_dirs, repo_name
from feedback_inbox.tests.test_support import make_bundle

if TYPE_CHECKING:
    from feedback_inbox._paths import Paths


def test_feedback_dirs_covers_every_game(paths: Paths) -> None:
    make_bundle(paths.data_root, game="cleanup-plate")
    make_bundle(paths.data_root, game="dread-grid")
    (paths.data_root / "other" / "feedback").mkdir(parents=True)
    (paths.data_root / "empty_binaries").mkdir()
    (paths.data_root / "file_binaries").write_text("x", encoding="utf-8")
    found = feedback_dirs(paths.data_root)
    assert [repo_name(d) for d in found] == ["cleanup-plate", "dread-grid"]


def test_feedback_dirs_without_data_root(paths: Paths) -> None:
    assert feedback_dirs(paths.data_root / "missing") == []


def test_bundles_in_keeps_only_stamp_folders(paths: Paths) -> None:
    first = make_bundle(paths.data_root, stamp="2026-11-11T13-53-19-124")
    make_bundle(paths.data_root, stamp="2026-11-11T13-52-33-162")
    feedback = first.parent
    (feedback / "notes").mkdir()
    (feedback / "2026-11-11T13-52-33-999").write_text("x", encoding="utf-8")
    names = [b.name for b in bundles_in(feedback)]
    assert names == ["2026-11-11T13-52-33-162", "2026-11-11T13-53-19-124"]


def test_due_is_next_day_ten(paths: Paths) -> None:
    assert due_at("2026-11-11T13-52-33-162") == datetime(2026, 11, 12, 10, 0)
    assert due_at("2026-12-31T23-59-59-001") == datetime(2027, 1, 1, 10, 0)
