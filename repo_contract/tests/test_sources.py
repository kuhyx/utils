"""Command sources: doc, Makefile, package.json, CI."""

from __future__ import annotations

from pathlib import Path

from repo_contract.sources import (
    ci_commands,
    doc_commands,
    first_match,
    make_targets,
    package_scripts,
    read_text,
)

from .conftest import write


def test_read_text_missing(tmp_path: Path) -> None:
    assert read_text(tmp_path / "x") == ""
    (tmp_path / "d").mkdir()
    assert read_text(tmp_path / "d") == ""


def test_doc_commands() -> None:
    assert doc_commands("use `pytest -q` and `scripts/x.sh` and `~/a b` and `one`") == [
        "pytest -q"
    ]


def test_make_targets(tmp_path: Path) -> None:
    write(tmp_path, "Makefile", "CC := gcc\ntest:\n\tx\nlint-all: y\n")
    assert make_targets(tmp_path) == {"test", "lint-all"}


def test_package_scripts(tmp_path: Path) -> None:
    assert package_scripts(tmp_path) == {}
    write(tmp_path, "package.json", "{bad")
    assert package_scripts(tmp_path) == {}
    write(tmp_path, "package.json", "[1]")
    assert package_scripts(tmp_path) == {}
    write(tmp_path, "package.json", '{"scripts": 3}')
    assert package_scripts(tmp_path) == {}
    write(tmp_path, "package.json", '{"scripts": {"test": "jest"}}')
    assert package_scripts(tmp_path) == {"test": "jest"}


def test_ci_commands(tmp_path: Path) -> None:
    write(
        tmp_path,
        ".github/workflows/ci.yml",
        "steps:\n  - run: pytest -q\n  - run: |\n      multi\n  - run: echo ${{ x }}\n    run: ruff check .\n",
    )
    assert ci_commands(tmp_path) == ["pytest -q", "ruff check ."]


def test_first_match() -> None:
    cmds = ["flutter test --coverage", "flutter test", "ruff check ."]
    assert first_match("test", cmds) == "flutter test"
    assert first_match("coverage", cmds) == "flutter test --coverage"
    assert first_match("lint", cmds) == "ruff check ."
    assert first_match("run", cmds) is None
    assert first_match("lint", ["x"]) is None
