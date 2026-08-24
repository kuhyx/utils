"""The gate itself: the three rules and the CLI."""

from __future__ import annotations

from pathlib import Path

import pytest

from md_naming import check
from md_naming.tests.conftest import write


def test_absolutize_leaves_absolute_alone() -> None:
    assert check.absolutize(Path("/a/b.md")) == Path("/a/b.md")


def test_absolutize_anchors_relative(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert check.absolutize(Path("b.md")) == tmp_path / "b.md"


def test_good_todo_has_no_violations(tmp_path: Path) -> None:
    path = write(tmp_path, "TODO-a.md", "# a\n\nREMOVE ME AFTER FINISH\n")
    assert check.violations_for(path) == []


def test_todo_without_marker(tmp_path: Path) -> None:
    path = write(tmp_path, "TODO-a.md", "# a\n")
    (problem,) = check.violations_for(path)
    assert "must contain" in problem


def test_marker_outside_todo(tmp_path: Path) -> None:
    path = write(tmp_path, "DOCS-a.md", "REMOVE ME AFTER FINISH\n")
    (problem,) = check.violations_for(path)
    assert "not named TODO" in problem


def test_bad_name(tmp_path: Path) -> None:
    path = write(tmp_path, "notes.md", "# a\n")
    (problem,) = check.violations_for(path)
    assert "must start with" in problem


def test_exempt_name_skips_naming_but_not_marker(tmp_path: Path) -> None:
    """A reserved name carrying the marker is a task in disguise."""
    clean = write(tmp_path, "CONTRIBUTING.md", "# c\n")
    assert check.violations_for(clean) == []

    sneaky = write(tmp_path, "SECURITY.md", "REMOVE ME AFTER FINISH\n")
    (problem,) = check.violations_for(sneaky)
    assert "not named TODO" in problem


def test_non_markdown_ignored(tmp_path: Path) -> None:
    path = write(tmp_path, "script.py", "REMOVE ME AFTER FINISH\n")
    assert check.violations_for(path) == []


def test_main_clean_tree(repo: Path, monkeypatch, capsys) -> None:
    write(repo, "README.md")
    write(repo, "TODO-a.md", "REMOVE ME AFTER FINISH\n")
    monkeypatch.chdir(repo)
    monkeypatch.setattr("sys.argv", ["check", "--all"])
    assert check.main() == 0
    assert capsys.readouterr().err == ""


def test_main_reports_violations(repo: Path, monkeypatch, capsys) -> None:
    write(repo, "notes.md")
    monkeypatch.chdir(repo)
    monkeypatch.setattr("sys.argv", ["check", "--all"])
    assert check.main() == 1
    assert "must start with" in capsys.readouterr().err


def test_main_named_paths(repo: Path, monkeypatch, capsys) -> None:
    write(repo, "notes.md")
    monkeypatch.chdir(repo)
    monkeypatch.setattr("sys.argv", ["check", "notes.md"])
    assert check.main() == 1
    assert "must start with" in capsys.readouterr().err


def test_main_requires_arguments(repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(repo)
    monkeypatch.setattr("sys.argv", ["check"])
    with pytest.raises(SystemExit):
        check.main()


def test_main_skips_directories(repo: Path, monkeypatch) -> None:
    (repo / "notes.md").mkdir()
    monkeypatch.chdir(repo)
    monkeypatch.setattr("sys.argv", ["check", "--all"])
    assert check.main() == 0


def test_named_path_that_is_a_directory(repo: Path, monkeypatch) -> None:
    """A directory reaching the loop is skipped, not crashed on.

    collect() normally filters these, so the guard in main() is reached only
    when collect yields one -- which is exactly what a symlinked or
    concurrently-replaced path does in real use.
    """
    (repo / "docs").mkdir()
    monkeypatch.chdir(repo)
    monkeypatch.setattr("sys.argv", ["check", "--all"])
    monkeypatch.setattr(check, "collect", lambda *a: [repo / "docs"])
    assert check.main() == 0


def test_collect_skips_non_files(repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(repo)
    parser = check.argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args(["missing.md"])
    assert check.collect(args, parser) == []
