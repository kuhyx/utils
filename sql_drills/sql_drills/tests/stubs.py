"""Shared stubs for the ``run_problem`` tests: a scripted sandbox, no Docker."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from sql_drills import _dialect
from sql_drills._sandbox import Executed

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    import pytest

STATEMENTS = Path(__file__).parent / "statements"
MONTHS = [
    f"{m}_Revenue"
    for m in [
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    ]
]
GOOD_ROWS = [
    ["1", "8000", "7000", "6000", *["NULL"] * 9],
    ["2", "9000", *["NULL"] * 11],
    ["3", "NULL", "10000", *["NULL"] * 10],
]


class StubBox:
    def __init__(self, done: Executed) -> None:
        self.done = done
        self.sqls: list[str] = []

    def query(self, sql: str) -> Executed:
        self.sqls.append(sql)
        return self.done


def install(
    monkeypatch: pytest.MonkeyPatch, done: Executed
) -> tuple[list[str], list[StubBox]]:
    schemas: list[str] = []
    boxes: list[StubBox] = []

    @contextmanager
    def fake(schema_sql: str) -> Iterator[StubBox]:
        schemas.append(schema_sql)
        box = StubBox(done)
        boxes.append(box)
        yield box

    def pick(dialect: str) -> Callable[[str], object]:
        schemas.append(f"dialect={dialect}")
        return fake

    monkeypatch.setattr(_dialect, "sandbox_for", pick)
    return schemas, boxes


def done(columns: list[str], rows: list[list[str]]) -> Executed:
    return Executed(ok=True, error=None, code=None, rows=rows, columns=columns)


def statement(slug: str) -> str:
    return (STATEMENTS / f"{slug}.txt").read_text()
