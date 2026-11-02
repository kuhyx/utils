"""Static integrity of the shipped builtin drills (no Docker)."""

from __future__ import annotations

import json
import re

import pytest

import sql_drills as sd
from sql_drills import _paths

ROOT = _paths.builtin_dir()
IDS = [m.id for m in sd.list_drills()]
# Drill content stays generic: no judge or employer names in what users read.
_BRANDS = re.compile(r"hackerrank|leetcode|google|amazon|meta\b|company", re.IGNORECASE)


@pytest.mark.parametrize("drill_id", IDS)
def test_folder_has_every_file(drill_id: str) -> None:
    names = {p.name for p in (ROOT / drill_id).iterdir()}
    required = {
        "meta.json",
        "DOCS-task.md",
        "schema.sql",
        "expected.txt",
        "tables.json",
    }
    assert required <= names
    kind = json.loads((ROOT / drill_id / "meta.json").read_text())["kind"]
    assert ("query.sql" in names) == (kind == "predict")


@pytest.mark.parametrize("drill_id", IDS)
def test_text_is_generic(drill_id: str) -> None:
    for path in (ROOT / drill_id).glob("*"):
        assert not _BRANDS.search(path.read_text()), path


@pytest.mark.parametrize("drill_id", IDS)
def test_expected_is_not_empty_and_tables_cover_schema(drill_id: str) -> None:
    folder = ROOT / drill_id
    assert (folder / "expected.txt").read_text().strip()
    schema = (folder / "schema.sql").read_text()
    for name in sd.get_drill(drill_id).tables:
        assert f"CREATE TABLE {name}" in schema


def test_every_write_drill_has_a_reference_solution() -> None:
    solutions = ROOT.parent / "tests" / "solutions"
    for meta in sd.list_drills():
        if meta.kind == "write":
            assert (solutions / f"{meta.id}.sql").is_file()


def test_exactly_one_builtin_error_drill() -> None:
    errors = [
        i
        for i in IDS
        if "error_code" in json.loads((ROOT / i / "meta.json").read_text())
    ]
    assert errors == ["t06_alias_in_where"]
