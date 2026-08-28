"""The unreadable, the malformed and the empty.

Every parser has to survive junk: the gate runs from a pre-commit hook, and a
traceback there blocks a commit for a reason the user cannot act on.
"""

from __future__ import annotations

from dep_freshness.parsers import fvm, javascript, pubspec, python, rust
from dep_freshness.tests.conftest import write


def test_a_missing_pubspec_yields_nothing(tmp_path):
    assert pubspec.parse(tmp_path / "nope.yaml") == []


def test_malformed_yaml_yields_nothing(tmp_path):
    assert pubspec.parse(write(tmp_path, "pubspec.yaml", "a: [\n")) == []


def test_a_yaml_scalar_document_yields_nothing(tmp_path):
    assert pubspec.parse(write(tmp_path, "pubspec.yaml", "just a string\n")) == []


def test_a_path_dependency_has_nothing_to_compare(tmp_path):
    body = "name: d\ndependencies:\n  local:\n    path: ../local\n"
    assert pubspec.parse(write(tmp_path, "pubspec.yaml", body)) == []


def test_a_null_constraint_is_read_as_unpinned(tmp_path):
    body = "name: d\ndependencies:\n  http:\n"
    assert pubspec.parse(write(tmp_path, "pubspec.yaml", body))[0].pinned is None


def test_a_missing_lock_is_an_empty_mapping(tmp_path):
    assert pubspec.locked_versions(tmp_path / "pubspec.lock") == {}


def test_malformed_toml_yields_nothing(tmp_path):
    assert python.parse_pyproject(write(tmp_path, "pyproject.toml", "[a\n")) == []
    assert rust.parse(write(tmp_path, "Cargo.toml", "[a\n")) == []


def test_a_missing_requirements_file_yields_nothing(tmp_path):
    assert python.parse_requirements(tmp_path / "nope.txt") == []


def test_requirements_skips_urls_flags_and_local_paths(tmp_path):
    body = "-r base.txt\ngit+https://x/y\nhttps://x/y.whl\n./local\n/abs/path\n"
    assert python.parse_requirements(write(tmp_path, "requirements.txt", body)) == []


def test_python_version_file_is_read_as_a_pin(tmp_path):
    dep = python.parse_python_version(write(tmp_path, ".python-version", "3.14.7\n"))
    assert dep[0].pinned == "3.14.7"


def test_an_empty_python_version_file_yields_nothing(tmp_path):
    assert python.parse_python_version(write(tmp_path, ".python-version", "")) == []


def test_nvmrc_is_read_as_a_pin(tmp_path):
    dep = javascript.parse_nvmrc(write(tmp_path, ".nvmrc", "v24.20.0\n"))
    assert dep[0].pinned == "24.20.0"


def test_an_empty_nvmrc_yields_nothing(tmp_path):
    assert javascript.parse_nvmrc(write(tmp_path, ".nvmrc", "\n")) == []


def test_malformed_json_yields_nothing(tmp_path):
    assert javascript.parse_package_json(write(tmp_path, "package.json", "{")) == []
    assert javascript.parse_package_json(
        write(tmp_path, "package.json", "[1, 2]")) == []


def test_a_non_string_dependency_spec_is_skipped(tmp_path):
    body = '{"dependencies": {"weird": {"version": "1.0.0"}}}'
    assert javascript.parse_package_json(write(tmp_path, "package.json", body)) == []


def test_an_fvmrc_that_is_not_an_object_yields_nothing(tmp_path):
    assert fvm.parse(write(tmp_path, ".fvmrc", "[]")) == []
    assert fvm.parse(write(tmp_path, ".fvmrc", "{")) == []
    assert fvm.parse(write(tmp_path, ".fvmrc", '{"flutter": ""}')) == []


def test_a_cargo_dependency_with_no_version_is_skipped(tmp_path):
    body = '[dependencies]\nx = { features = ["a"] }\n'
    assert rust.parse(write(tmp_path, "Cargo.toml", body)) == []


def test_line_index_of_an_unreadable_file_is_empty(tmp_path):
    from dep_freshness.parsers._lines import find, index
    assert index(tmp_path / "nope") == {}
    assert find(tmp_path / "nope", "x") == 0
