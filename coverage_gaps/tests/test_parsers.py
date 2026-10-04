"""Parser and format-detection tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from coverage_gaps.models import FileGap, ReportError
from coverage_gaps.parsers import detect_format, load_report


def _by_path(gaps: list[FileGap]) -> dict[str, FileGap]:
    return {gap.path: gap for gap in gaps}


@pytest.mark.parametrize("fmt", ["lcov", "cobertura", "json"])
def test_a_py_gaps_match_across_formats(reports: dict[str, Path], fmt: str) -> None:
    detected, gaps = load_report(reports[fmt])
    assert detected == fmt
    a = _by_path(gaps)["a.py"]
    assert a.missed_lines == (2, 3, 5)
    assert a.missed_branch_lines == (4,)
    assert a.missed_branches == 1
    assert a.total_lines == 5
    assert a.total_branches == 2
    assert _by_path(gaps)["b.py"].missed == 0


def test_jacoco(reports: dict[str, Path]) -> None:
    fmt, gaps = load_report(reports["jacoco"])
    assert fmt == "jacoco"
    by = _by_path(gaps)
    assert by["com/x/A.kt"].missed_lines == (2, 3, 5)
    assert by["com/x/A.kt"].missed_branch_lines == (4,)
    assert by["com/x/A.kt"].total_branches == 2
    assert "Top.kt" in by


def test_percent_and_empty_file() -> None:
    gap = FileGap("x", 4, (1,), 4, (2,), 1)
    assert gap.percent == 75.0
    assert FileGap("y", 0, (), 0, (), 0).percent == 100.0


def test_lcov_ignores_records_outside_a_file_and_dash_branch_ids() -> None:
    from coverage_gaps.parsers import parse_lcov

    gaps = parse_lcov(
        "DA:1,0\nBRDA:1,0,0,0\nSF:z\nBRDA:2,0,-,0\nend_of_record\nDA:9,0\n"
    )
    assert len(gaps) == 1
    assert gaps[0].missed_lines == ()
    assert gaps[0].missed_branch_lines == (2,)


def test_detect_unknown_and_xml_without_known_root() -> None:
    for text in ("hello", "<other/>", ""):
        with pytest.raises(ReportError):
            detect_format(text)


def test_load_errors(tmp_path: Path) -> None:
    with pytest.raises(ReportError, match="cannot read"):
        load_report(tmp_path / "missing")
    bad_xml = tmp_path / "bad.xml"
    bad_xml.write_text("<coverage><oops", encoding="utf-8")
    with pytest.raises(ReportError, match="malformed cobertura"):
        load_report(bad_xml)
    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{nope", encoding="utf-8")
    with pytest.raises(ReportError, match="malformed json"):
        load_report(bad_json)
