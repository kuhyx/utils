"""Which files the gate picks up, and which it deliberately does not."""

from __future__ import annotations

from pathlib import Path

import pytest

from dep_freshness.discover import find_manifests, is_manifest, parse_manifest
from dep_freshness.tests.conftest import write

PUBSPEC = "name: demo\ndependencies:\n  http: 1.6.0\n"


@pytest.mark.parametrize("name", [
    "pubspec.yaml", "pyproject.toml", "package.json", "Cargo.toml", "go.mod",
    ".fvmrc", ".nvmrc", ".python-version", "requirements.txt",
    "requirements-dev.txt",
])
def test_manifest_names_are_recognised(name):
    assert is_manifest(Path(name))


@pytest.mark.parametrize("name", ["main.dart", "README.md", "pubspec.lock",
                                  "my-requirements.md"])
def test_other_files_are_not_manifests(name):
    assert not is_manifest(Path(name))


def test_find_manifests_walks_the_tree(repo):
    write(repo, "pubspec.yaml", PUBSPEC)
    write(repo, "packages/core/pubspec.yaml", PUBSPEC)
    write(repo, "lib/main.dart", "void main() {}\n")
    found = {p.name for p in find_manifests(repo)}
    assert found == {"pubspec.yaml"}
    assert len(find_manifests(repo)) == 2


def test_excluded_directories_are_skipped(repo):
    write(repo, "build/pubspec.yaml", PUBSPEC)
    write(repo, "node_modules/x/package.json", "{}")
    write(repo, ".dart_tool/pubspec.yaml", PUBSPEC)
    assert find_manifests(repo) == []


def test_git_ignored_manifests_are_skipped(repo):
    write(repo, ".gitignore", "generated/\n")
    write(repo, "generated/pubspec.yaml", PUBSPEC)
    write(repo, "pubspec.yaml", PUBSPEC)
    assert [p.name for p in find_manifests(repo)] == ["pubspec.yaml"]
    assert all("generated" not in str(p) for p in find_manifests(repo))


def test_outside_a_git_repo_nothing_is_treated_as_ignored(tmp_path):
    write(tmp_path, "pubspec.yaml", PUBSPEC)
    assert len(find_manifests(tmp_path)) == 1


def test_symlinked_manifests_are_skipped(repo):
    write(repo, "real/pubspec.yaml", PUBSPEC)
    (repo / "pubspec.yaml").symlink_to(repo / "real" / "pubspec.yaml")
    assert [str(p) for p in find_manifests(repo)] == [
        str(repo / "real" / "pubspec.yaml")
    ]


def test_parse_manifest_routes_by_filename(tmp_path):
    path = write(tmp_path, "requirements-dev.txt", "ruff==0.16.5\n")
    assert [d.name for d in parse_manifest(path)] == ["ruff"]


def test_parse_manifest_ignores_anything_else(tmp_path):
    assert parse_manifest(write(tmp_path, "main.dart", "void main() {}")) == []
