"""LeetCode statement text to ASCII tables (``+---+`` / ``| a |`` blocks)."""

from __future__ import annotations

from dataclasses import dataclass
import html
import re

_BREAKS = re.compile(r"</?(?:p|div|pre|li|ul|ol|br|h\d)\b[^>]*>", re.IGNORECASE)
_TAGS = re.compile(r"</?[a-zA-Z][a-zA-Z0-9]*(?:\s[^<>]*)?/?>")
_HTML = re.compile(r"</(?:p|pre|div|code|strong|li|ul)>", re.IGNORECASE)
_MARKS = re.compile(r"\*\*|`")


@dataclass(frozen=True)
class Grid:
    columns: list[str]
    rows: list[list[str]]


@dataclass(frozen=True)
class Found:
    start: int
    end: int
    grid: Grid


def to_text(statement: str) -> str:
    """Plain lines from fetched markdown or raw statement HTML."""
    text = statement
    if _HTML.search(statement):
        text = html.unescape(_TAGS.sub("", _BREAKS.sub("\n", statement)))
    text = text.replace("\r", "").replace("\xa0", " ")
    return _MARKS.sub("", text).strip()


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _grid(block: list[str]) -> Grid | None:
    data = [_cells(ln) for ln in block if not ln.startswith("+")]
    if not data or any(len(row) != len(data[0]) for row in data):
        return None
    return Grid(data[0], data[1:])


def find_tables(lines: list[str]) -> list[Found]:
    """Every well-formed table block; ragged or header-less blocks are skipped."""
    found: list[Found] = []
    start: int | None = None
    for i, raw in enumerate([*lines, ""]):
        if raw.strip().startswith(("+", "|")):
            start = i if start is None else start
            continue
        if start is not None:
            grid = _grid([ln.strip() for ln in lines[start:i]])
            if grid is not None:
                found.append(Found(start, i, grid))
            start = None
    return found
