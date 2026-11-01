"""Tests for scripts/conformance_diff.py (100 % branch coverage)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import conformance_diff
import pytest

if TYPE_CHECKING:
    from pathlib import Path


def previous_report(conf: float | None = 50.0) -> dict:
    return {
        "surfaces": [{"name": ".", "token_usages": 1, "raw_literals": 1, "conformance": conf}],
        "totals": {"name": "TOTAL", "token_usages": 1, "raw_literals": 1, "conformance": conf},
    }


def current_report() -> dict:
    return {
        "surfaces": [
            {"name": ".", "files": 1, "token_usages": 3, "raw_literals": 1, "conformance": 75.0},
            {"name": "new", "files": 1, "token_usages": 2, "raw_literals": 0, "conformance": None},
        ],
        "totals": {"name": "TOTAL", "files": 2, "token_usages": 5, "raw_literals": 1, "conformance": 83.3},
    }


def test_delta_rows() -> None:
    rows = {r["name"]: r for r in conformance_diff.delta(current_report(), previous_report())["rows"]}
    assert rows["."] == {"name": ".", "token_usages": 2.0, "raw_literals": 0.0, "conformance": 25.0}
    assert rows["new"]["token_usages"] == 2.0
    assert rows["new"]["conformance"] is None
    assert rows["TOTAL"]["conformance"] == 33.3


def test_delta_missing_previous_conformance() -> None:
    rows = conformance_diff.delta(current_report(), previous_report(None))["rows"]
    assert rows[0]["conformance"] is None


def test_num_and_fmt() -> None:
    assert conformance_diff._num("x") == 0.0
    assert conformance_diff._num(2) == 2.0
    assert conformance_diff._fmt(None) == "-"
    assert conformance_diff._fmt(2.5) == "2.5"
    assert conformance_diff._fmt(2, signed=True) == "+2"


def test_table_without_and_with_delta() -> None:
    plain = conformance_diff.table(current_report(), None)
    assert plain.splitlines()[0].split() == ["surface", "files", "tokens", "raw", "conf%"]
    assert "TOTAL" in plain
    diff = conformance_diff.delta(current_report(), previous_report())
    text = conformance_diff.table(current_report(), diff)
    assert "d.conf" in text
    assert "+25" in text


@pytest.mark.parametrize(
    "payload",
    ["[]", "{}", '{"surfaces": 1, "totals": {}}', '{"surfaces": [1], "totals": {}}',
     '{"surfaces": [], "totals": 1}'],
)
def test_load_previous_rejects_bad_shape(tmp_path: Path, payload: str) -> None:
    path = tmp_path / "p.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError, match="not a conformance report"):
        conformance_diff.load_previous(path)
