"""Manifest parsing, including the shapes that used to crash the gate.

`plugin_platform_interface: any` and a `requirements.txt` of bare names were
the two Phase-0 "the gate cannot even parse these" cases. They parse now, and
land as findings — a gate that dies on the input it exists to police is worse
than no gate.
"""

from __future__ import annotations

from dep_freshness.parsers import fvm, javascript, pubspec, python, rust
from dep_freshness.tests.conftest import write

PUBSPEC = """\
name: demo
environment:
  sdk: ^3.12.2
dependencies:
  flutter:
    sdk: flutter
  http: 1.6.0
  plugin_platform_interface: any
  crdt_sync:
    git:
      url: https://github.com/kuhyx/utils
      ref: crdt_sync_dart-v0.11.0
      path: crdt_sync_dart
dev_dependencies:
  flutter_test:
    sdk: flutter
  very_good_analysis: ^10.2.0
dependency_overrides:
  meta: 1.16.0
"""


def _by_name(deps):
    return {d.name: d for d in deps}


def test_pubspec_reads_every_dependency_shape(tmp_path):
    deps = _by_name(pubspec.parse(write(tmp_path, "pubspec.yaml", PUBSPEC)))
    assert deps["http"].pinned == "1.6.0"
    assert deps["plugin_platform_interface"].pinned is None
    assert deps["crdt_sync_dart"].ecosystem == "gittag"
    assert deps["crdt_sync_dart"].pinned == "0.11.0"
    assert deps["dart"].constraint == "^3.12.2"
    assert deps["very_good_analysis"].caret_ok
    assert deps["meta"].override


def test_pubspec_skips_sdk_packages(tmp_path):
    deps = _by_name(pubspec.parse(write(tmp_path, "pubspec.yaml", PUBSPEC)))
    assert "flutter" not in deps
    assert "flutter_test" not in deps


def test_a_missing_lockfile_is_a_library_not_a_violation(tmp_path):
    """Four of the nine shared libs gitignore their lock on purpose."""
    deps = _by_name(pubspec.parse(write(tmp_path, "pubspec.yaml", PUBSPEC)))
    assert deps["http"].locked is None


def test_pubspec_reads_the_lockfile_when_one_is_committed(tmp_path):
    write(tmp_path, "pubspec.yaml", PUBSPEC)
    write(tmp_path, "pubspec.lock", "packages:\n  http:\n    version: \"1.5.0\"\n")
    deps = _by_name(pubspec.parse(tmp_path / "pubspec.yaml"))
    assert deps["http"].locked == "1.5.0"


def test_line_numbers_prefer_the_least_indented_key(tmp_path):
    """A nested `path:` inside a git block must not win over the real dep."""
    body = PUBSPEC.replace("  http: 1.6.0", "  path: 1.9.1\n  http: 1.6.0")
    deps = _by_name(pubspec.parse(write(tmp_path, "pubspec.yaml", body)))
    assert deps["path"].line == 7  # not the nested `path:` in the git block


def test_requirements_bare_names_parse_as_unpinned(tmp_path):
    path = write(tmp_path, "requirements.txt", "numpy\npillow\n# a comment\n-e .\n")
    deps = python.parse_requirements(path)
    assert [d.name for d in deps] == ["numpy", "pillow"]
    assert all(d.pinned is None for d in deps)


def test_requirements_handles_extras_markers_and_pins(tmp_path):
    path = write(
        tmp_path, "requirements.txt",
        'ruff==0.16.5\nuvicorn[standard]==0.30.0\nfoo>=1.0 ; python_version>"3.9"\n',
    )
    deps = {d.name: d for d in python.parse_requirements(path)}
    assert deps["ruff"].pinned == "0.16.5"
    assert deps["uvicorn"].pinned == "0.30.0"
    assert deps["foo"].pinned is None


def test_pyproject_reads_project_and_group_dependencies(tmp_path):
    path = write(tmp_path, "pyproject.toml", """\
[project]
requires-python = ">=3.10"
dependencies = ["httpx==0.28.1"]
[project.optional-dependencies]
dev = ["pytest==8.4.2"]
[dependency-groups]
lint = ["ruff==0.16.5"]
""")
    deps = {d.name: d for d in python.parse_pyproject(path)}
    assert deps["httpx"].pinned == "0.28.1"
    assert deps["pytest"].pinned == "8.4.2"
    assert deps["ruff"].pinned == "0.16.5"
    assert deps["python"].constraint == ">=3.10"


def test_package_json_reads_engines_and_overrides(tmp_path):
    path = write(tmp_path, "package.json", """\
{"engines": {"node": "24.20.0"},
 "dependencies": {"react": "19.2.0", "local": "workspace:*"},
 "devDependencies": {"vitest": "^4.1.10"},
 "resolutions": {"semver": "7.7.1"}}
""")
    deps = {d.name: d for d in javascript.parse_package_json(path)}
    assert deps["node"].pinned == "24.20.0"
    assert deps["react"].pinned == "19.2.0"
    assert "local" not in deps
    assert deps["vitest"].pinned is None
    assert deps["semver"].override


def test_cargo_treats_a_two_part_version_as_a_range(tmp_path):
    path = write(tmp_path, "Cargo.toml", """\
[dependencies]
serde = "1.0.229"
loose = "1.0"
local = { path = "../x" }
tabled = { version = "0.20.0" }
""")
    deps = {d.name: d for d in rust.parse(path)}
    assert deps["serde"].pinned == "1.0.229"
    assert deps["loose"].pinned is None
    assert deps["tabled"].pinned == "0.20.0"
    assert "local" not in deps


def test_fvmrc_channel_is_not_a_version(tmp_path):
    channel = fvm.parse(write(tmp_path, ".fvmrc", '{"flutter": "stable"}'))
    assert channel[0].pinned is None
    pinned = fvm.parse(write(tmp_path, ".fvmrc", '{"flutter": "3.47.2"}'))
    assert pinned[0].pinned == "3.47.2"
