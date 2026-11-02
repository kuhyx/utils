"""SQL problems state the OUTPUT SHAPE (columns, rows, grouping) before any code.

The SQL counterpart of the ``req:`` gate: a ``shape:`` message is judged
mechanically (no model, nothing to fail open), and the verdict rides the same
``req`` / ``req_check`` log events (``via: "shape"``), so readers need no change.
"""

from __future__ import annotations

import re
from typing import Final

from leetcode_coach import req_check

VIA: Final = "shape"
SHAPE_RE: Final = re.compile(r"^\s*shape\s*:", re.IGNORECASE)
SQL_LANGS: Final = frozenset(
    {"mysql", "mssql", "oraclesql", "postgresql", "pythondata"}
)
LANGUAGES_RE: Final = re.compile(r"^Languages available:(.*)$", re.MULTILINE)
TAGS_RE: Final = re.compile(r"^Tags:(.*)$", re.MULTILINE)
FACETS: Final = {
    "columns": (
        re.compile(r"\b(?:columns?|fields?|headers?|named)\b", re.IGNORECASE),
        "which columns come back, named how",
    ),
    "rows": (
        re.compile(r"\b(?:rows?|records?|per)\b", re.IGNORECASE),
        "what one row stands for (one row per ...)",
    ),
    "grouping": (
        re.compile(
            r"\b(?:group\w*|aggregat\w*|distinct|unique|per|sum|count|ungrouped)\b",
            re.IGNORECASE,
        ),
        "how rows are grouped or aggregated, or that nothing is",
    ),
}


def _items(line: re.Match[str] | None) -> set[str]:
    return set() if line is None else {p.strip() for p in line.group(1).split(",")}


def is_sql(statement: str) -> bool:
    """A rendered statement offers a SQL dialect or carries the Database tag."""
    langs = _items(LANGUAGES_RE.search(statement))
    return bool(langs & SQL_LANGS) or "Database" in _items(TAGS_RE.search(statement))


def missing_facets(text: str) -> tuple[str, ...]:
    return tuple(name for name, (found, _) in FACETS.items() if not found.search(text))


def check(text: str) -> req_check.Check:
    missing = missing_facets(text)
    return req_check.Check("incomplete" if missing else "pass", missing, VIA)


def hints(missing: tuple[str, ...] | list[str]) -> list[str]:
    return [f"{name}: {FACETS[name][1]}" for name in missing if name in FACETS]
