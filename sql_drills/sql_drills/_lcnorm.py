"""LeetCode/HackerRank-style comparison: values, not formatting.

NULL is case-blind, numbers compare by value (``0.50`` == ``0.5``), booleans
compare as 1/0 (PostgreSQL prints ``t``/``f``), trailing blanks are ignored, row
order is ignored unless the statement demands it. Column names are not judged.
"""

from __future__ import annotations

from decimal import Decimal
import re
from typing import TYPE_CHECKING

from sql_drills._normalize import Comparison, Rows, compare

if TYPE_CHECKING:
    from sql_drills._dialect import Dialect

_NUMBER = re.compile(r"[+-]?\d+(\.\d+)?([eE][+-]?\d+)?")
_BOOLS = {"true": "1", "false": "0"}
_PG_BOOLS = {"t": "1", "f": "0"}


def canon(cell: str, dialect: Dialect) -> str:
    text = cell.rstrip()
    low = text.lower()
    if low == "null":
        return "NULL"
    if low in _BOOLS or (dialect == "postgresql" and low in _PG_BOOLS):
        return _BOOLS.get(low) or _PG_BOOLS[low]
    if _NUMBER.fullmatch(text):
        value = Decimal(text)
        return "0" if value == 0 else format(value.normalize(), "f")
    return text


def compare_results(
    expected: Rows,
    actual: Rows,
    dialect: Dialect,
    *,
    ordered: bool,
    subset: bool = False,
) -> Comparison:
    """Compare canonical cells; ``subset`` = the expected rows are a sample.

    With ``ordered=False`` both sides are sorted first, so ``cell_diff`` rows
    index the sorted order.
    """
    exp = [[canon(c, dialect) for c in row] for row in expected]
    act = [[canon(c, dialect) for c in row] for row in actual]
    if not ordered:
        exp, act = sorted(exp), sorted(act)
    got = compare(exp, act)
    if not subset:
        return got
    return Comparison(
        match=not got.missing_rows,
        cell_diff=got.cell_diff if got.missing_rows else [],
        extra_rows=[],
        missing_rows=got.missing_rows,
    )
