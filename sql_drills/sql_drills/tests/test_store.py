"""Drill discovery over the builtin fixtures and the generated data dir."""

from __future__ import annotations

from dataclasses import asdict
import json
from typing import TYPE_CHECKING

import pytest

import sql_drills as sd
from sql_drills import _paths

if TYPE_CHECKING:
    from pathlib import Path

SOLUTIONS = _paths.builtin_dir().parent / "tests" / "solutions"


def _make_generated(root: Path, drill_id: str, *, kind: str = "write") -> None:
    folder = root / "drills" / drill_id
    folder.mkdir(parents=True)
    (folder / "meta.json").write_text(json.dumps({"kind": kind, "topic": "window"}))
    (folder / "DOCS-task.md").write_text("# Made up\n\nBody\n")
    (folder / "schema.sql").write_text("CREATE TABLE t (a INT);")
    (folder / "expected.txt").write_text("1\n2\n")
    (folder / "tables.json").write_text(
        json.dumps({"t": {"columns": ["a"], "rows": [["1"], ["2"]]}})
    )


def test_topics_are_the_contract_list() -> None:
    assert sd.topics() == [
        "basics",
        "pivot",
        "dates",
        "number-format",
        "joins-null",
        "group-having",
        "window",
        "strings",
    ]


def test_builtin_list_has_twelve_write_and_seven_predict() -> None:
    metas = sd.list_drills()
    assert [m.kind for m in metas].count("write") == 12
    assert [m.kind for m in metas].count("predict") == 7
    assert {m.source for m in metas} == {"builtin"}
    assert {m.topic for m in metas} <= set(sd.TOPICS)
    assert [m.id for m in metas] == sorted(m.id for m in metas)


def test_titles_come_from_the_task_heading() -> None:
    by_id = {m.id: m for m in sd.list_drills()}
    assert by_id["01_pivot_sum"].title.startswith("Pivot quarters")
    assert by_id["t01_null_not_equal"].title == "Predict: NULL and !="


def test_theory_drills_are_basics() -> None:
    topics = {m.topic for m in sd.list_drills() if m.id.startswith("t")}
    assert topics == {"basics"}


def test_generated_drills_follow_builtin_ones() -> None:
    _make_generated(_paths.data_dir(), "g-window-abc12345")
    metas = sd.list_drills()
    assert metas[-1].id == "g-window-abc12345"
    assert metas[-1].source == "generated"
    assert metas[-1].title == "Made up"


def test_dirs_without_meta_are_ignored() -> None:
    (_paths.data_dir() / "drills" / ".tmp-partial").mkdir(parents=True)
    assert all(m.source == "builtin" for m in sd.list_drills())


def test_get_write_drill() -> None:
    drill = sd.get_drill("01_pivot_sum")
    assert drill.meta.kind == "write"
    assert "CREATE TABLE shop_sales" in drill.schema_sql
    assert drill.task_md.startswith("# Pivot")
    assert drill.query is None
    assert 0 < len(drill.expected_preview) <= 5
    assert drill.tables["shop_sales"].columns == ["id", "region", "quarter", "amount"]
    assert len(drill.tables["shop_sales"].rows) == 10


def test_get_predict_drill_shows_query_but_no_expected() -> None:
    drill = sd.get_drill("t03_left_join_on")
    assert drill.meta.kind == "predict"
    assert drill.query is not None
    assert "LEFT JOIN" in drill.query
    assert drill.expected_preview == []
    assert set(drill.tables) == {"customers", "orders"}


def test_number_prefix_resolves_builtin_ids() -> None:
    assert sd.get_drill("03").meta.id == "03_month_bucket"
    assert sd.get_drill("t05").meta.id == "t05_anti_join"


def test_generated_drill_by_exact_id_only() -> None:
    _make_generated(_paths.data_dir(), "g-window-abc12345")
    assert sd.get_drill("g-window-abc12345").meta.source == "generated"
    with pytest.raises(sd.UnknownDrillError):
        sd.get_drill("g")


def test_unknown_drill_raises() -> None:
    with pytest.raises(sd.UnknownDrillError, match="nope"):
        sd.get_drill("nope")


def _strings(obj: object) -> list[str]:
    if isinstance(obj, str):
        return [" ".join(obj.split())]
    if isinstance(obj, dict):
        return [t for v in obj.values() for t in _strings(v)]
    if isinstance(obj, list):
        return [t for v in obj for t in _strings(v)]
    return []


def test_public_drills_never_contain_reference_sql() -> None:
    texts = [t for m in sd.list_drills() for t in _strings(asdict(sd.get_drill(m.id)))]
    solutions = list(SOLUTIONS.glob("*.sql"))
    assert len(solutions) == 12
    for solution in solutions:
        body = " ".join(solution.read_text().split())
        assert not any(body in text for text in texts)
