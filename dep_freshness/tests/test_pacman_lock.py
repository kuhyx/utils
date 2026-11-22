"""A pacman-repo lock: parsed, discovered, and judged end to end.

The consumer is steam-game-installer's `steam_installer/data/proton-native.lock`,
which pins one package out of the CachyOS repo. Pre-commit hands the gate the
file by name, so `is_manifest` must accept it on content, not on a glob.
"""

from __future__ import annotations

import json

import pytest

from dep_freshness import check, discover
from dep_freshness.models import Severity
from dep_freshness.parsers import pacman_lock
from dep_freshness.registries import pacman_repo
from dep_freshness.tests.conftest import write
from dep_freshness.tests.test_pacman_repo import SHA, build_db

REPO = "https://mirror.cachyos.org/repo/x86_64/cachyos/cachyos.db"
LOCK = f"""\
# pacman-repo lock: newest stable package from an Arch-style repo db
name=proton-cachyos-native
repo={REPO}
version=1:11.0.20261015-1
sha256={SHA}
"""
LOCK_PATH = "steam_installer/data/proton-native.lock"


def test_the_lock_parses_to_one_pinned_dep(repo):
    path = write(repo, LOCK_PATH, LOCK)
    [dep] = pacman_lock.parse(path)
    assert dep.ecosystem == "pacman-repo"
    assert pacman_repo.split_name(dep.name) == (REPO, "proton-cachyos-native")
    assert dep.pinned == "1:11.0.20261015-1"
    assert dep.locked == SHA
    assert dep.line == 4  # the version= line is what a bump edits


@pytest.mark.parametrize(
    ("name", "body"),
    [
        ("Cargo.lock", '[[package]]\nname = "serde"\nversion = "1.0.0"\n'),
        ("other.lock", "name=x\nrepo=https://example.org/not-a-db.json\n"),
        ("proton-native.txt", LOCK),
    ],
)
def test_other_files_are_not_pacman_locks(repo, name, body):
    path = write(repo, name, body)
    assert not discover.is_manifest(path)
    assert discover.parse_manifest(path) == []


def test_the_lock_is_discovered_by_content(repo):
    path = write(repo, LOCK_PATH, LOCK)
    assert discover.is_manifest(path)
    assert path in discover.find_manifests(repo)


def test_a_lock_without_a_version_is_unpinned(repo):
    path = write(repo, "x.lock", LOCK.replace("version=1:11.0.20261015-1\n", ""))
    [dep] = pacman_lock.parse(path)
    assert dep.pinned is None


@pytest.fixture
def gate(repo, monkeypatch):
    """Run the CLI on the lock, with the repo db answering `served`."""
    def invoke(lock_body, served, *flags):
        name, version, sha = served
        body = build_db({name: version}, sha=sha)
        monkeypatch.setattr(pacman_repo, "get_bytes", lambda _url: body)
        path = write(repo, LOCK_PATH, lock_body)
        monkeypatch.chdir(repo)
        return check.main([*flags, str(path)])
    return invoke


CURRENT = ("proton-cachyos-native", "1:11.0.20261015-1", SHA)


def test_a_current_lock_passes(gate):
    assert gate(LOCK, CURRENT, "--strict") == 0


def test_a_lock_behind_the_repo_fails(gate, capsys):
    old = LOCK.replace("1:11.0.20261015-1", "1:10.0.20250101-1")
    assert gate(old, CURRENT) == 1
    out = capsys.readouterr()
    text = out.out + out.err
    assert "proton-cachyos-native" in text
    assert "1:11.0.20261015-1" in text
    assert SHA in text  # the bump is copy-pasteable


def test_an_epoch_beats_a_bigger_pkgver(gate):
    # PEP 440 would read `11.0` > `1:2.0` (or nothing at all); pacman says the
    # epoch wins, so a lock on 11.0 is behind a repo on 1:2.0.
    old = LOCK.replace("1:11.0.20261015-1", "11.0-1")
    assert gate(old, ("proton-cachyos-native", "1:2.0-1", SHA)) == 1


def test_a_right_version_with_a_wrong_sha_is_a_mismatch(gate, capsys):
    assert gate(LOCK, (*CURRENT[:2], "cd" * 32), "--json") == 1
    payload = json.loads(capsys.readouterr().out)
    assert Severity.LOCK_MISMATCH.value in json.dumps(payload)


def test_a_package_the_repo_dropped_is_undeterminable(gate):
    assert gate(LOCK, ("something-else", "1.0-1", SHA), "--strict") == 3


def test_offline_with_a_cold_cache_is_undeterminable(repo, monkeypatch):
    from dep_freshness.registries import http

    http.force_offline(True)
    path = write(repo, LOCK_PATH, LOCK)
    monkeypatch.chdir(repo)
    assert check.main(["--strict", str(path)]) == 3
    assert check.main([str(path)]) == 0  # pre-commit degrades, never corners


def test_zstd_on_an_old_python_is_undeterminable_not_a_crash(
    repo, monkeypatch, capsys
):
    body = build_db({"proton-cachyos-native": "1:11.0.20261015-1"}, "zst")
    monkeypatch.setattr(pacman_repo, "get_bytes", lambda _url: body)
    monkeypatch.setattr(pacman_repo, "_HAS_ZSTD", False)
    path = write(repo, LOCK_PATH, LOCK)
    monkeypatch.chdir(repo)
    assert check.main(["--strict", str(path)]) == 3
    out = capsys.readouterr()
    assert "compression.zstd" in out.out + out.err
