"""Stack detection and the test-presence probe."""

from __future__ import annotations

from pathlib import Path

import pytest

from repo_contract.stacks import MAX_DEPTH, detect_stacks, has_tests

from .conftest import write


def test_markers_detected(tmp_path: Path) -> None:
    write(tmp_path, "pubspec.yaml")
    write(tmp_path, "pyproject.toml")
    assert detect_stacks(tmp_path) == ["flutter", "python"]


def test_each_marker(tmp_path: Path) -> None:
    for name, stack in (
        ("project.godot", "godot"),
        ("go.mod", "go"),
        ("Cargo.toml", "rust"),
        ("build.gradle.kts", "gradle"),
        ("package.json", "node"),
    ):
        sub = tmp_path / stack
        write(sub, name)
        assert detect_stacks(sub) == [stack]


def test_shell_only_and_unknown(tmp_path: Path) -> None:
    assert detect_stacks(tmp_path) == []
    write(tmp_path, "scripts/a.sh")
    assert detect_stacks(tmp_path) == ["shell"]


def test_walk_prunes_and_bounds_depth(tmp_path: Path) -> None:
    write(tmp_path, "node_modules/x/y_test.py")
    deep = "/".join(["d"] * (MAX_DEPTH + 1))
    write(tmp_path, f"{deep}/test_deep.py")
    assert not has_tests(tmp_path, [])


def test_has_tests_by_dir_and_name(tmp_path: Path) -> None:
    write(tmp_path / "a", "tests/anything.txt")
    assert has_tests(tmp_path / "a", [])
    write(tmp_path / "b", "src/foo_test.go")
    assert has_tests(tmp_path / "b", [])
    write(tmp_path / "c", "test_x.py")
    assert has_tests(tmp_path / "c", [])
    write(tmp_path / "d", "src/a.py")
    assert not has_tests(tmp_path / "d", [])


def test_node_test_script(tmp_path: Path) -> None:
    write(tmp_path, "package.json", '{"scripts": {"test": "vitest"}}')
    assert has_tests(tmp_path, ["node"])
    write(tmp_path, "package.json", '{"scripts": {"test": "echo no test specified"}}')
    assert not has_tests(tmp_path, ["node"])
    assert not has_tests(tmp_path, ["python"])


def test_node_package_json_unreadable(tmp_path: Path) -> None:
    (tmp_path / "package.json").mkdir()
    assert not has_tests(tmp_path, ["node"])


def test_file_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from repo_contract import stacks

    monkeypatch.setattr(stacks, "MAX_FILES", 2)
    for i in range(5):
        write(tmp_path, f"f{i}.txt")
    assert len(stacks._walk(tmp_path)) >= 2
