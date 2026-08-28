"""End-to-end: a repo on disk in, an exit code out.

Both directions are asserted here on purpose. A freshness gate that returns 0
everywhere on day one is indistinguishable from one that checks nothing, and
this repo has shipped exactly that twice before (two fake file-length gates).
"""

from __future__ import annotations

from datetime import date, timedelta
import os

import pytest

from dep_freshness import check
from dep_freshness.cache import Cache
from dep_freshness.registries import http
from dep_freshness.tests.conftest import write

STALE_PUBSPEC = """\
name: demo
environment:
  sdk: ^3.12.2
dependencies:
  http: 1.5.0
"""
CURRENT_PUBSPEC = STALE_PUBSPEC.replace("1.5.0", "1.6.0")
ALLOWLIST = "dependency-freshness.allowlist.yaml"


@pytest.fixture(autouse=True)
def canned(monkeypatch, cache_dir):
    """One registry answer for every package the fixtures declare."""
    answers = {("pub", "http"): "1.6.0", ("toolchain", "dart"): "3.13.2"}
    monkeypatch.setattr(
        "dep_freshness.resolve._fetch",
        lambda eco, name: answers.get((eco, name)),
    )
    return answers


@pytest.fixture
def run(repo, monkeypatch):
    def invoke(*argv):
        monkeypatch.chdir(repo)
        return check.main(list(argv))
    return invoke


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


def test_a_transitive_exception_excuses_the_finding(repo, run):
    write(repo, "pubspec.yaml", STALE_PUBSPEC)
    write(repo, ALLOWLIST, """\
exceptions:
  - ecosystem: pub
    package: http
    pinned: "1.5.0"
    reason: "something upstream holds it"
    blocked_by: "transitive:some_pkg@1.0.0"
""")
    assert run("--all") == 0


def test_an_exception_prints_loudly_even_on_success(repo, run, capsys):
    test_a_transitive_exception_excuses_the_finding(repo, run)
    err = capsys.readouterr().err
    assert "DEPENDENCY EXCEPTION IN USE" in err
    assert "still blocking" in err


def test_an_exception_with_nothing_left_to_excuse_is_an_error(repo, run, capsys):
    write(repo, "pubspec.yaml", CURRENT_PUBSPEC)
    write(repo, ALLOWLIST, """\
exceptions:
  - ecosystem: pub
    package: http
    pinned: "1.5.0"
    reason: "stale entry nobody removed"
    blocked_by: "transitive:some_pkg@1.0.0"
""")
    assert run("--all") == 2
    assert "no longer stale" in capsys.readouterr().err


def test_an_expired_allowlist_exits_two(repo, run, capsys):
    write(repo, "pubspec.yaml", STALE_PUBSPEC)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    write(repo, ALLOWLIST, f"""\
exceptions:
  - ecosystem: pub
    package: http
    pinned: "1.5.0"
    reason: "held"
    blocked_by: "discretionary"
    expires: "{yesterday}"
""")
    assert run("--all") == 2
    assert "Allowlist ERROR" in capsys.readouterr().err


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
