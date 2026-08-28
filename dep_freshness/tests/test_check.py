"""End-to-end: a repo on disk in, an exit code out.

Both directions are asserted here on purpose. A freshness gate that returns 0
everywhere on day one is indistinguishable from one that checks nothing, and
this repo has shipped exactly that twice before (two fake file-length gates).
"""

from __future__ import annotations

import os

import pytest

from dep_freshness import check
from dep_freshness.cache import Cache
from dep_freshness.registries import http
from dep_freshness.tests.conftest import (
    ALLOWLIST,
    CURRENT_PUBSPEC,
    STALE_PUBSPEC,
    write,
)


def test_a_stale_pin_fails_and_names_the_package(repo, run, capsys):
    write(repo, "pubspec.yaml", STALE_PUBSPEC)
    assert run("--all") == 1
    assert "pub:http" in capsys.readouterr().err


def test_a_current_repo_passes(repo, run):
    write(repo, "pubspec.yaml", CURRENT_PUBSPEC)
    assert run("--all") == 0


def test_named_paths_check_only_those_files(repo, run):
    write(repo, "pubspec.yaml", STALE_PUBSPEC)
    write(repo, "sub/pubspec.yaml", CURRENT_PUBSPEC)
    assert run("sub/pubspec.yaml") == 0
    assert run("pubspec.yaml") == 1


def test_a_non_manifest_path_is_ignored(repo, run):
    write(repo, "pubspec.yaml", STALE_PUBSPEC)
    write(repo, "lib/main.dart", "void main() {}\n")
    assert run("lib/main.dart") == 0


def test_offline_with_a_cold_cache_passes_with_a_degraded_banner(
    repo, run, capsys, monkeypatch
):
    """`--no-verify` is banned, so a hook must never corner the user offline."""
    monkeypatch.setattr("dep_freshness.resolve._fetch", _offline)
    write(repo, "pubspec.yaml", STALE_PUBSPEC)
    assert run("--all", "--offline") == 0
    assert "DEGRADED" in capsys.readouterr().err


def test_offline_with_a_cold_cache_fails_under_strict(repo, run, monkeypatch):
    """CI is always online, so an undeterminable answer there is a real failure."""
    monkeypatch.setattr("dep_freshness.resolve._fetch", _offline)
    write(repo, "pubspec.yaml", STALE_PUBSPEC)
    assert run("--all", "--offline", "--strict") == 3


def test_offline_with_a_warm_cache_still_finds_the_stale_pin(
    repo, run, monkeypatch, cache_dir
):
    cache = Cache(cache_dir / "registry.json")
    cache.put("pub", "http", "1.6.0")
    cache.put("toolchain", "dart", "3.13.2")
    cache.save()
    monkeypatch.setattr("dep_freshness.resolve._fetch", _offline)
    write(repo, "pubspec.yaml", STALE_PUBSPEC)
    assert run("--all", "--offline") == 1


def test_exceptions_only_reports_the_allowlist_and_stops(repo, run, capsys):
    write(repo, "pubspec.yaml", STALE_PUBSPEC)
    write(repo, ALLOWLIST, """\
exceptions:
  - ecosystem: pub
    package: http
    pinned: "1.5.0"
    latest_known: "1.6.0"
    reason: "held"
    blocked_by: "transitive:some_pkg@1.0.0"
""")
    assert run("--exceptions-only") == 0
    assert "[DEP-EXCEPTION] pub:http 1.5.0 < 1.6.0" in capsys.readouterr().err


def test_json_output_carries_the_exit_code(repo, run, capsys):
    write(repo, "pubspec.yaml", STALE_PUBSPEC)
    assert run("--all", "--json") == 1
    assert '"exit_code": 1' in capsys.readouterr().out


def test_no_target_at_all_is_a_usage_error(run):
    with pytest.raises(SystemExit):
        run()


def test_repo_root_falls_back_outside_a_git_repo(tmp_path):
    assert check.repo_root(tmp_path) == tmp_path


def _offline(_ecosystem, _name):
    raise http.Offline("no network")


def test_the_cache_directory_is_honoured(cache_dir):
    assert os.environ["DEP_FRESHNESS_CACHE"] == str(cache_dir)
