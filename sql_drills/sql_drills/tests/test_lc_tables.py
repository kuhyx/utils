"""Statement text to ASCII tables."""

from __future__ import annotations

from sql_drills import _lc_tables as lt

BORDER = "+----+-----+"


def test_to_text_strips_markdown_marks() -> None:
    assert lt.to_text("**Input:** `x`\r\nrow") == "Input: x\nrow"


def test_to_text_converts_html() -> None:
    html = (
        "<p><strong>Input:</strong>&nbsp;</p><pre>Dept table:<br>"
        "+----+<br>| id |<br>+----+</pre><p>a &lt; b</p>"
    )
    text = lt.to_text(html)
    assert "Input:" in text
    assert "+----+\n| id |\n+----+" in text
    assert "a < b" in text


def test_find_tables_parses_header_rows_and_empty_cells() -> None:
    lines = [
        "intro",
        BORDER,
        "| id | n   |",
        BORDER,
        "| 1  | a b |",
        "| 2  |     |",
        BORDER,
        "tail",
    ]
    (found,) = lt.find_tables(lines)
    assert (found.start, found.end) == (1, 7)
    assert found.grid.columns == ["id", "n"]
    assert found.grid.rows == [["1", "a b"], ["2", ""]]


def test_find_tables_handles_two_tables_and_header_only() -> None:
    lines = [BORDER, "| a | b |", BORDER, "", BORDER, "| c | d |", BORDER, "| 1 | 2 |"]
    first, second = lt.find_tables(lines)
    assert first.grid.rows == []
    assert second.grid.rows == [["1", "2"]]


def test_ragged_or_headerless_blocks_are_not_tables() -> None:
    ragged = [BORDER, "| a | b |", BORDER, "| 1 |", BORDER]
    borders_only = [BORDER, BORDER]
    assert lt.find_tables(ragged) == []
    assert lt.find_tables(borders_only) == []


def test_to_text_keeps_comparison_operators() -> None:
    line = "1 <= n <= 100 and a<b and y > 2"
    assert lt.to_text(line) == line
