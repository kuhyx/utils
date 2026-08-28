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


def test_a_config_block_never_wins_the_line_over_the_dependency(tmp_path):
    """Every Flutter app here declares `flutter_launcher_icons` twice.

    Once as a dev dependency, and once as a TOP-LEVEL configuration block for
    the same tool. Least-indented wins sends the fix to the config block --
    lyricanki reported `pubspec.yaml:64`, the config key, while the version
    being complained about lives at line 48.
    """
    body = """\
name: demo
environment:
  sdk: ^3.12.2
dependencies:
  flutter:
    sdk: flutter
dev_dependencies:
  flutter_launcher_icons: ^0.14.4

flutter_launcher_icons:
  android: true
  image_path: "assets/icon/icon.png"
"""
    deps = {
        d.name: d
        for d in pubspec.parse(write(tmp_path, "pubspec.yaml", body))
    }
    assert deps["flutter_launcher_icons"].line == 8


def test_the_sdk_line_is_the_environment_one_not_a_plugin_block(tmp_path):
    """`flutter: {sdk: flutter}` also declares an `sdk:` key, deeper in."""
    body = """\
name: demo
environment:
  sdk: ^3.12.2
dependencies:
  flutter:
    sdk: flutter
"""
    deps = {
        d.name: d
        for d in pubspec.parse(write(tmp_path, "pubspec.yaml", body))
    }
    assert deps["dart"].line == 3


DIRECT_REQ = """\
ruff==0.16.5
crdt-sync @ git+https://github.com/kuhyx/utils@crdt-sync-v0.9.0#subdirectory=crdt-sync
gatelock @ git+https://github.com/kuhyx/utils@gatelock-v0.7.1#subdirectory=gatelock
"""


def test_a_git_direct_reference_is_a_git_tag_dependency(tmp_path):
    """The shared Python libs are consumed by git tag, like the Dart ones.

    Parsed as an ordinary requirement this is an unpinned PyPI package that
    does not exist on PyPI, so the answer is undeterminable and the drift is
    invisible -- wake-alarm sat four minor versions behind on both with a
    green gate.
    """
    deps = {
        d.name: d
        for d in python.parse_requirements(
            write(tmp_path, "requirements.txt", DIRECT_REQ)
        )
    }
    assert deps["crdt-sync"].ecosystem == "gittag"
    assert deps["crdt-sync"].pinned == "0.9.0"
    assert deps["crdt-sync"].line == 2
    assert deps["gatelock"].pinned == "0.7.1"
    assert deps["ruff"].ecosystem == "pypi"


def test_a_pyproject_git_direct_reference_is_a_git_tag_dependency(tmp_path):
    body = """\
[project]
name = "demo"
requires-python = ">=3.13"
dependencies = [
  "gatelock @ git+https://github.com/kuhyx/utils@gatelock-v0.7.1#subdirectory=gatelock",
]
"""
    deps = {
        d.name: d
        for d in python.parse_pyproject(write(tmp_path, "pyproject.toml", body))
    }
    assert deps["gatelock"].ecosystem == "gittag"
    assert deps["gatelock"].pinned == "0.7.1"
    assert deps["gatelock"].line == 5


def test_a_plain_git_url_without_a_version_tag_is_still_skipped(tmp_path):
    """A branch or SHA ref has no version to compare, so it stays unparsed."""
    body = "thing @ git+https://github.com/kuhyx/utils@main#subdirectory=thing\n"
    assert python.parse_requirements(
        write(tmp_path, "requirements.txt", body)
    )[0].ecosystem == "pypi"


def test_an_unreadable_manifest_gives_the_direct_reference_no_line(tmp_path):
    """`_ref_line` degrades to 0 rather than raising, like the key indexer."""
    missing = tmp_path / "gone.txt"
    assert python._ref_line(missing, "gatelock-v0.7.1") == 0


def test_a_direct_reference_the_file_does_not_contain_has_no_line(tmp_path):
    path = write(tmp_path, "requirements.txt", "ruff==0.16.5\n")
    assert python._ref_line(path, "gatelock-v0.7.1") == 0
