"""Exact-match judge rules (tabs to spaces, rstrip) plus a cell-level diff."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import zip_longest
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sql_drills._model import CellDiff

Rows = list[list[str]]


def parse_rows(text: str) -> Rows:
    return [ln.split("\t") for ln in text.splitlines()]


def line(cells: list[str]) -> str:
    return "\t".join(cells).replace("\t", " ").rstrip()


def clean_grid(grid: Rows) -> Rows:
    rows = [[cell.strip() for cell in row] for row in grid]
    while rows and not any(rows[-1]):
        rows.pop()
    return rows


def _trim(cells: list[str] | None) -> list[str]:
    out = [c.rstrip() for c in cells or []]
    while out and not out[-1]:
        out.pop()
    return out


@dataclass(frozen=True)
class Comparison:
    match: bool
    cell_diff: list[CellDiff]
    extra_rows: Rows
    missing_rows: Rows


def _cell_diff(expected: Rows, actual: Rows) -> list[CellDiff]:
    diffs: list[CellDiff] = []
    for r, (exp_row, act_row) in enumerate(zip_longest(expected, actual)):
        pairs = zip_longest(_trim(exp_row), _trim(act_row))
        diffs.extend((r, c, e, a) for c, (e, a) in enumerate(pairs) if e != a)
    return diffs


def _surplus(left: Rows, right: Rows) -> Rows:
    spare = Counter(line(r) for r in right)
    out: Rows = []
    for row in left:
        key = line(row)
        if spare[key] > 0:
            spare[key] -= 1
        else:
            out.append(row)
    return out


def compare(expected: Rows, actual: Rows) -> Comparison:
    if [line(r) for r in expected] == [line(r) for r in actual]:
        return Comparison(match=True, cell_diff=[], extra_rows=[], missing_rows=[])
    return Comparison(
        match=False,
        cell_diff=_cell_diff(expected, actual),
        extra_rows=_surplus(actual, expected),
        missing_rows=_surplus(expected, actual),
    )
