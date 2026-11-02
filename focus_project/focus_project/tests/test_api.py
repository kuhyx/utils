# Copyright (c) 2026 Krzysztof Rudnicki
"""Registry, active/stands_down, create/end/list."""

from __future__ import annotations

from datetime import date, timedelta
import json
from typing import TYPE_CHECKING
from unittest import mock

import pytest

import focus_project as fp
from focus_project._errors import RegistryError

if TYPE_CHECKING:
    from pathlib import Path

D1 = date(2026, 11, 2)
D4 = date(2026, 11, 5)


def _make(
    pid: str = "hr", start: date = D1, end: date = D4, **kw: object
) -> fp.Project:
    args: dict[str, object] = {
        "name": "HackerRank prep",
        "replaces": ["leetcode", "reading", "tutor"],
        "daily_minutes": 120,
        "unlock_minutes": 30,
    }
    args.update(kw)
    return fp.create_project(pid, start=start, end=end, **args)  # type: ignore[arg-type]


def test_empty_registry() -> None:
    assert fp.list_projects() == []
    assert fp.active(D1) is None
    assert fp.stands_down("leetcode", D1) is False


def test_create_roundtrip_and_file_shape(data: Path) -> None:
    p = _make(subjects=["a"], site_patterns=["leetcode.com"])
    assert fp.list_projects() == [p]
    raw = json.loads((data / "projects.json").read_text())
    row = raw["projects"][0]
    assert row["id"] == "hr"
    assert row["start"] == "2026-11-02"
    assert row["replaces"] == ["leetcode", "reading", "tutor"]
    assert row["ended_on"] is None
    assert row["created_ms"] > 0
    assert row["subjects"] == ["a"]
    assert not list(data.glob("*.tmp"))


def test_active_boundaries() -> None:
    _make()
    assert fp.active(D1 - timedelta(days=1)) is None
    assert fp.active(D1).id == "hr"  # type: ignore[union-attr]
    assert fp.active(D4).id == "hr"  # type: ignore[union-attr]
    assert fp.active(D4 + timedelta(days=1)) is None


def test_stands_down_matrix() -> None:
    _make()
    assert fp.stands_down("leetcode", D1) is True
    assert fp.stands_down("book", D1) is True
    assert fp.stands_down("reading", D1) is True
    assert fp.stands_down("tutor", D1) is True
    assert fp.stands_down("workout", D1) is False
    assert fp.stands_down("leetcode", D4 + timedelta(days=1)) is False


def test_book_alias_in_replaces() -> None:
    _make(replaces=["book"])
    assert fp.list_projects()[0].replaces == ("reading",)
    assert fp.stands_down("book", D1) is True
    assert fp.stands_down("leetcode", D1) is False


def test_overlap_rejected_and_adjacent_ok() -> None:
    _make()
    with pytest.raises(ValueError, match="overlap"):
        _make("other", start=D4, end=D4 + timedelta(days=2))
    _make("next", start=D4 + timedelta(days=1), end=D4 + timedelta(days=2))
    assert len(fp.list_projects()) == 2


def test_end_early_frees_later_days() -> None:
    _make()
    ended = fp.end_project("hr", D1 + timedelta(days=1))
    assert ended.ended_on == D1 + timedelta(days=1)
    assert fp.active(D1 + timedelta(days=1)) is not None
    assert fp.active(D1 + timedelta(days=2)) is None
    assert fp.stands_down("leetcode", D1 + timedelta(days=2)) is False
    _make("again", start=D1 + timedelta(days=2), end=D4)


def test_end_project_errors() -> None:
    _make()
    with pytest.raises(KeyError):
        fp.end_project("nope", D1)
    with pytest.raises(ValueError, match="before"):
        fp.end_project("hr", D1 - timedelta(days=1))
    fp.end_project("hr", D4 + timedelta(days=9))  # clamps to the planned end
    assert fp.list_projects()[0].ended_on == D4
    with pytest.raises(ValueError, match="already"):
        fp.end_project("hr", D1)


@pytest.mark.parametrize(
    ("kw", "match"),
    [
        ({"pid": "Bad Id"}, "id"),
        ({"end": D1 - timedelta(days=1)}, "end"),
        ({"replaces": ["workout"]}, "gate"),
        ({"replaces": []}, "replace"),
        ({"daily_minutes": 0}, "daily_minutes"),
        ({"unlock_minutes": 121}, "unlock_minutes"),
        ({"unlock_minutes": -1}, "unlock_minutes"),
        ({"name": " "}, "name"),
    ],
)
def test_create_validation(kw: dict[str, object], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        _make(**kw)  # type: ignore[arg-type]
    assert fp.list_projects() == []


def test_duplicate_id_rejected() -> None:
    _make()
    with pytest.raises(ValueError, match="exists"):
        _make(start=D4 + timedelta(days=5), end=D4 + timedelta(days=6))


def test_corrupt_registry_raises_but_stands_down_fails_closed(data: Path) -> None:
    data.mkdir()
    (data / "projects.json").write_text("{not json")
    with pytest.raises(RegistryError):
        fp.list_projects()
    assert fp.stands_down("leetcode", D1) is False


@pytest.mark.parametrize(
    "body", ['{"projects": [{"id": "x"}]}', "[]", '{"projects": 3}']
)
def test_bad_shapes(data: Path, body: str) -> None:
    data.mkdir()
    (data / "projects.json").write_text(body)
    with pytest.raises(RegistryError):
        fp.list_projects()


def test_overlapping_file_is_corrupt_for_active(data: Path) -> None:
    _make()
    raw = json.loads((data / "projects.json").read_text())
    raw["projects"].append({**raw["projects"][0], "id": "dup"})
    (data / "projects.json").write_text(json.dumps(raw))
    with pytest.raises(RegistryError, match="overlap"):
        fp.active(D1)
    assert fp.stands_down("leetcode", D1) is False


def test_failed_write_keeps_old_file(data: Path) -> None:
    _make()
    before = (data / "projects.json").read_text()
    with (
        mock.patch("focus_project._store.os.replace", side_effect=OSError("boom")),
        pytest.raises(OSError, match="boom"),
    ):
        _make("two", start=D4 + timedelta(days=3), end=D4 + timedelta(days=4))
    assert (data / "projects.json").read_text() == before
    assert not list(data.glob("*.tmp"))
