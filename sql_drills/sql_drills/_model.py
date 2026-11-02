"""Public data types; none can carry a drill's reference SQL."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Kind = Literal["write", "predict"]
Source = Literal["builtin", "generated"]
CellDiff = tuple[int, int, str | None, str | None]  # row, col, expected, actual

TOPICS: tuple[str, ...] = (
    "basics",
    "pivot",
    "dates",
    "number-format",
    "joins-null",
    "group-having",
    "window",
    "strings",
)


class UnknownDrillError(KeyError):
    pass


class DrillKindError(ValueError):
    pass


@dataclass(frozen=True)
class DrillMeta:
    id: str
    title: str
    topic: str
    kind: Kind
    source: Source


@dataclass(frozen=True)
class Table:
    columns: list[str]
    rows: list[list[str]]


@dataclass(frozen=True)
class Drill:
    meta: DrillMeta
    task_md: str
    schema_sql: str
    tables: dict[str, Table]
    expected_preview: list[list[str]]  # write drills only; [] for predict
    query: str | None  # predict drills only: the SQL to predict


@dataclass(frozen=True)
class RunResult:
    ok: bool
    error: str | None
    columns: list[str]
    rows: list[list[str]]
    expected_rows: list[list[str]]
    match: bool
    cell_diff: list[CellDiff] = field(default_factory=list)
    extra_rows: list[list[str]] = field(default_factory=list)
    missing_rows: list[list[str]] = field(default_factory=list)
    note: str | None = None  # e.g. the statement's output elides columns


@dataclass(frozen=True)
class PredResult:
    match: bool
    cell_diff: list[CellDiff]
    actual_rows: list[list[str]]
    error: str | None = None  # the real MySQL message, error drills only
    extra_rows: list[list[str]] = field(default_factory=list)
    missing_rows: list[list[str]] = field(default_factory=list)
