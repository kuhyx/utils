"""Command inference."""

from __future__ import annotations

from pathlib import Path

from repo_contract.infer import propose, quiet, stack_defaults

from .conftest import write


def test_quiet() -> None:
    assert quiet("pytest -v tests") == "pytest -q tests"
    assert quiet("pytest -q") == "pytest -q"
    assert quiet("flutter test") == "flutter test --reporter=compact"
    assert quiet("flutter test -r expanded") == "flutter test -r expanded"
    assert quiet("x --reporter=expanded") == "x "
    assert quiet("go test ./...") == "go test ./..."


def test_python_defaults_and_launchers(tmp_path: Path) -> None:
    write(tmp_path, "pyproject.toml", "[tool.ruff]\n")
    assert stack_defaults(tmp_path, "python")["lint"] == "ruff check ."
    write(tmp_path, "uv.lock")
    assert stack_defaults(tmp_path, "python")["test"] == "uv run pytest -q"
    assert stack_defaults(tmp_path, "python")["lint"] == "uv run ruff check ."
    (tmp_path / "uv.lock").unlink()
    write(tmp_path, "poetry.lock")
    assert stack_defaults(tmp_path, "python")["test"].startswith("poetry run")


def test_python_no_ruff_and_run_default(tmp_path: Path) -> None:
    write(tmp_path, "pyproject.toml")
    write(tmp_path, "tests/test_a.py")
    write(tmp_path, "main.py")
    prop = propose(tmp_path, ["python"])
    assert prop.values["lint"] == "`pre-commit run --all-files`"
    assert prop.values["run"] == "`python3 main.py`"
    assert prop.values["coverage-gaps"] == "`coverage-gaps coverage.xml`"
    assert prop.values["test-changed"] == "`scripts/test_changed.sh`"
    assert prop.lines()[0].startswith("- run:")


def test_run_defaults_with_entry_points(tmp_path: Path) -> None:
    write(tmp_path, "tests/a.txt")
    for stack, marker, expected in (
        ("go", "main.go", "go run ."),
        ("rust", "src/main.rs", "cargo run"),
        ("gradle", "app/x", "./gradlew installDebug"),
        ("shell", "x.sh", "n/a: collection of scripts"),
    ):
        write(tmp_path, marker)
        assert propose(tmp_path, [stack]).values["run"].strip("`").startswith(expected)


def test_library_run_is_na(tmp_path: Path) -> None:
    write(tmp_path, "tests/a.txt")
    for stack in ("python", "go", "rust", "gradle", "node"):
        assert propose(tmp_path, [stack]).values["run"].startswith("n/a: library")


def test_stack_defaults_each(tmp_path: Path) -> None:
    write(tmp_path, "tests/a.txt")
    write(tmp_path, "pnpm-lock.yaml")
    for stack in ("flutter", "node", "go", "rust", "gradle"):
        prop = propose(tmp_path, [stack])
        assert prop.values["test"].startswith("`")
        assert "coverage-gaps " in prop.values["coverage-gaps"]
    write(tmp_path, "yarn.lock")
    (tmp_path / "pnpm-lock.yaml").unlink()
    assert propose(tmp_path, ["node"]).values["test"].startswith("`yarn")
    (tmp_path / "yarn.lock").unlink()
    assert propose(tmp_path, ["node"]).values["test"].startswith("`npm")


def test_priority_doc_make_helper_npm_ci(tmp_path: Path) -> None:
    write(tmp_path, "tests/a.txt")
    write(tmp_path, "package.json", '{"scripts": {"test": "x", "lint": "y"}}')
    assert propose(tmp_path, ["node"]).values["lint"] == "`npm run lint`"
    write(tmp_path, "scripts/lint.sh")
    assert propose(tmp_path, ["node"]).values["lint"] == "`scripts/lint.sh`"
    write(tmp_path, "Makefile", "lint:\n\tx\n")
    assert propose(tmp_path, ["node"]).values["lint"] == "`make lint`"
    write(tmp_path, "CLAUDE.md", "Lint with `eslint . -v`.\n")
    assert propose(tmp_path, ["node"]).values["lint"] == "`eslint .`"
    write(tmp_path, ".github/workflows/a.yml", "- run: go test -v ./...\n")
    assert propose(tmp_path, ["go"]).values["test"] == "`go test ./...`"


def test_untested_godot_and_shell_are_na(tmp_path: Path) -> None:
    write(tmp_path, "project.godot")
    prop = propose(tmp_path, ["godot"])
    assert prop.values["test"].startswith("n/a")
    assert prop.values["test-changed"].startswith("n/a")
    assert any("no tests detected" in n for n in prop.notes)
    assert propose(tmp_path, []).stack == "unknown"


def test_godot_with_runner(tmp_path: Path) -> None:
    write(tmp_path, "tests/test_a.gd")
    write(tmp_path, "addons/gut/gut_cmdln.gd")
    prop = propose(tmp_path, ["godot"])
    assert "gut_cmdln" in prop.values["test"]
    assert prop.values["coverage-gaps"].startswith("n/a")
    (tmp_path / "addons/gut/gut_cmdln.gd").unlink()
    (tmp_path / "addons/gdUnit4").mkdir()
    assert "GdUnitCmdTool" in propose(tmp_path, ["godot"]).values["test"]
    (tmp_path / "addons/gdUnit4").rmdir()
    assert propose(tmp_path, ["godot"]).values["test"] == "`<FILL IN>`"


def test_unknown_report_and_untested_note(tmp_path: Path) -> None:
    write(tmp_path, "scripts/a.sh")
    prop = propose(tmp_path, ["python"])
    assert any("no tests detected, but" in n for n in prop.notes)
    write(tmp_path, "tests/a.txt")
    write(tmp_path, "Makefile", "coverage:\n\tx\n")
    shell = propose(tmp_path, ["shell"])
    assert shell.values["coverage"].startswith("`make coverage")
    assert shell.values["coverage-gaps"] == "`<FILL IN>`"
    assert any("fill in" in n for n in shell.notes)
