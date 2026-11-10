# Copyright (c) 2026 Krzysztof Rudnicki
"""The append-only evidence store and record_evidence validation."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

import focus_project as fp
from focus_project import _paths, evidence
from focus_project.tests.helpers import at, make, shot

if TYPE_CHECKING:
    from pathlib import Path


def test_paths_are_isolated(tmp_path: Path) -> None:
    assert _paths.evidence_dir().is_relative_to(tmp_path)
    assert _paths.evidence_path("iv").name == "iv.jsonl"
    assert _paths.evidence_files_dir("iv").name == "iv"


def test_file_is_copied_and_row_appended(tmp_path: Path) -> None:
    make()
    src = shot(tmp_path)
    row = fp.record_evidence("iv", "rules", "file", file=src, now=at(10, 9))
    assert row.kind == "file"
    stored = _paths.evidence_files_dir("iv") / str(row.value)
    assert stored.read_bytes() == src.read_bytes()
    line = json.loads(_paths.evidence_path("iv").read_text().splitlines()[0])
    assert set(line) == {"ms", "milestone", "kind", "value"}
    assert line["milestone"] == "rules"


def test_rows_append_never_rewrite() -> None:
    make()
    fp.record_evidence("iv", "mock", "score", 71, now=at(24, 9))
    fp.record_evidence("iv", "mock", "score", 80.5, now=at(24, 10))
    assert [r.value for r in evidence.read("iv")] == [71, 80.5]
    assert not hasattr(fp, "delete_evidence")
    assert not hasattr(evidence, "delete")


def test_same_name_files_do_not_overwrite(tmp_path: Path) -> None:
    make()
    one = fp.record_evidence("iv", "rules", "file", file=shot(tmp_path), now=at(10, 9))
    two = fp.record_evidence("iv", "rules", "file", file=shot(tmp_path), now=at(10, 9))
    assert one.value != two.value


@pytest.mark.parametrize(
    ("milestone", "kind", "value"),
    [
        ("rules", "tap", True),  # wrong kind for the milestone
        ("rules", "check", True),  # internal kind
        ("trip_ask:2026-11-14", "answer", True),  # use answer_weekend
        ("nope", "tap", True),  # not a milestone of the project
        ("mock", "score", "high"),
        ("mock", "score", True),
        ("mock", "score", float("nan")),
        ("mock", "score", -1),
        ("slot", "slot", "tomorrow"),
        ("slot", "slot", "2026-11-26T10:00:00+02:00"),  # aware
        ("slot", "slot_confirm", False),
        ("phone", "phone_check", {"plan": True}),
        ("phone", "phone_check", {"plan": "yes", "due": 1, "seen_ms": 1}),
        ("phone", "phone_check", "ok"),
    ],
)
def test_bad_evidence_refused(milestone: str, kind: str, value: object) -> None:
    make()
    with pytest.raises(ValueError):  # noqa: PT011
        fp.record_evidence("iv", milestone, kind, value, now=at(12, 9))


def test_file_kind_needs_a_real_nonempty_file(tmp_path: Path) -> None:
    make()
    empty = tmp_path / "e.png"
    empty.write_bytes(b"")
    for bad in (None, tmp_path / "missing.png", empty, tmp_path):
        with pytest.raises(ValueError, match="file"):
            fp.record_evidence("iv", "rules", "file", file=bad, now=at(10, 9))


def test_unknown_project_is_keyerror() -> None:
    with pytest.raises(KeyError):
        fp.record_evidence("ghost", "mock", "score", 1, now=at(24, 9))


def test_focus_project_has_no_milestones() -> None:
    fp.create_project(
        "f",
        name="F",
        start=at(10).date(),
        end=at(12).date(),
        replaces=["leetcode"],
        daily_minutes=30,
        unlock_minutes=10,
    )
    with pytest.raises(ValueError, match="milestone"):
        fp.record_evidence("f", "mock", "score", 1, now=at(10, 9))


def test_torn_and_foreign_lines_are_skipped(caplog: pytest.LogCaptureFixture) -> None:
    make()
    fp.record_evidence("iv", "mock", "score", 70, now=at(24, 9))
    path = _paths.evidence_path("iv")
    path.write_text(path.read_text() + '{"ms": 1, "milest\n[1]\n{"ms":"x"}\n')
    with caplog.at_level("WARNING"):
        rows = evidence.read("iv")
    assert [r.value for r in rows] == [70]
    assert "skipping" in caplog.text


def test_missing_file_reads_empty() -> None:
    assert evidence.read("nobody") == []


def test_garbage_bytes_are_skipped_not_fatal() -> None:
    make()
    fp.record_evidence("iv", "mock", "score", 70, now=at(24, 9))
    path = _paths.evidence_path("iv")
    path.write_bytes(path.read_bytes() + b"\xff\xfe\x80 not utf-8\n")
    assert [r.value for r in evidence.read("iv")] == [70]
