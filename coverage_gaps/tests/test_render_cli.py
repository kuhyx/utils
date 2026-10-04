"""Rendering, filtering and CLI exit-code tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from coverage_gaps.cli import main
from coverage_gaps.models import FileGap
from coverage_gaps.render import compact_ranges, select, to_markdown


def test_compact_ranges() -> None:
    assert compact_ranges([]) == ""
    assert compact_ranges([40, 12, 13, 14, 15, 16, 17, 18, 18]) == "12-18, 40"
    assert compact_ranges([1, 3, 5, 6]) == "1, 3, 5-6"


def test_select_sorts_and_filters() -> None:
    small = FileGap("src/b.py", 5, (1,), 0, (), 0)
    big = FileGap("lib/a.py", 5, (1, 2), 2, (3,), 1)
    clean = FileGap("src/c.py", 5, (), 0, (), 0)
    assert [g.path for g in select([small, clean, big])] == ["lib/a.py", "src/b.py"]
    assert [g.path for g in select([small, big], path_prefix="src")] == ["src/b.py"]
    assert [g.path for g in select([small, big], min_missed=2)] == ["lib/a.py"]


def test_markdown_branch_only_gap() -> None:
    out = to_markdown("lcov", [FileGap("z.py", 2, (), 2, (7,), 1)], 1)
    assert "- missed lines" not in out
    assert "missed branches (1) at lines: 7" in out


def test_module_entrypoint(
    reports: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    import runpy

    monkeypatch.setattr("sys.argv", ["coverage_gaps", str(reports["lcov"])])
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("coverage_gaps", run_name="__main__")
    assert exc.value.code == 1


def test_markdown_no_gaps() -> None:
    assert "No coverage gaps." in to_markdown("lcov", [], 0)


@pytest.mark.parametrize("fmt", ["lcov", "cobertura", "jacoco", "json"])
def test_cli_markdown_exit_1(
    reports: dict[str, Path], fmt: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([str(reports[fmt])]) == 1
    out = capsys.readouterr().out
    assert "2-3, 5" in out
    assert "missed branches (1) at lines: 4" in out
    assert "b.py" not in out.replace("A.kt", "")


def test_cli_json_and_max_files(
    reports: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([str(reports["jacoco"]), "--json", "--max-files", "1"]) == 1
    doc = json.loads(capsys.readouterr().out)
    assert doc["shown"] == 1
    assert doc["total"] == {"files": 1, "missed_lines": 3, "missed_branches": 1}
    assert doc["files"][0]["missed_lines"] == "2-3, 5"


def test_cli_markdown_truncation_note(
    reports: dict[str, Path], capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    two = tmp_path / "two.info"
    two.write_text("SF:x\nDA:1,0\nend_of_record\nSF:y\nDA:1,0\nDA:2,0\nend_of_record\n")
    assert main([str(two), "--max-files", "1"]) == 1
    out = capsys.readouterr().out
    assert "Showing the 1 worst files." in out
    assert "`y`" in out
    assert "`x`" not in out


def test_cli_exit_0_when_filtered_clean(
    reports: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([str(reports["lcov"]), "--path-prefix", "b."]) == 0
    assert main([str(reports["lcov"]), "--json", "--min-missed", "99"]) == 0
    assert "No coverage gaps." in capsys.readouterr().out


def test_cli_exit_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(tmp_path / "nope")]) == 2
    junk = tmp_path / "junk"
    junk.write_text("junk")
    assert main([str(junk)]) == 2
    assert "coverage-gaps:" in capsys.readouterr().err
