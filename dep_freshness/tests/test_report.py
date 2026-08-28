"""Reporting, plumbing and entrypoint branches.

Split out of `test_edges.py` to hold every file under the shared 250-line cap;
same concern, second half. These cover the paths a happy-path run never takes:
git missing, a cleared exception, a malformed expiry, the module entrypoint.
"""

from __future__ import annotations

from datetime import date, timedelta
import io
from pathlib import Path
import subprocess

import pytest

from dep_freshness import check, discover, report, resolve
from dep_freshness.models import Dep, Exception_, Finding, Severity
from dep_freshness.registries.http import Offline
from dep_freshness.tests.conftest import write
from dep_freshness.versions import newest_stable


def test_git_check_ignore_missing_means_nothing_is_ignored(tmp_path, monkeypatch):
    def no_git(*_args, **_kwargs):
        raise OSError("no git")
    monkeypatch.setattr(subprocess, "run", no_git)
    assert discover._git_ignored([tmp_path / "pubspec.yaml"], tmp_path) == set()


def test_repo_root_falls_back_when_git_is_missing(tmp_path, monkeypatch):
    def no_git(*_args, **_kwargs):
        raise OSError("no git")
    monkeypatch.setattr(subprocess, "run", no_git)
    assert check.repo_root(tmp_path) == tmp_path


def test_fetch_dispatches_to_the_right_registry(monkeypatch):
    """`_LOOKUP` binds the adapters at import, so the dict is what to patch."""
    monkeypatch.setitem(resolve._LOOKUP, "pub", lambda name: f"pub-{name}")
    assert resolve._fetch("pub", "http") == "pub-http"
    assert resolve._fetch("nonsense", "x") is None


def test_fetch_routes_toolchain_names(monkeypatch):
    monkeypatch.setattr(resolve.tc, "node_latest", lambda: "24.20.0")
    assert resolve._fetch("toolchain", "node") == "24.20.0"


def test_exceptions_only_json_carries_the_entries(repo, monkeypatch, capsys):
    write(repo, "dependency-freshness.allowlist.yaml", """\
exceptions:
  - ecosystem: pub
    package: http
    pinned: "1.5.0"
    reason: "held"
    blocked_by: "transitive:x@1.0.0"
""")
    monkeypatch.chdir(repo)
    assert check.main(["--exceptions-only", "--json"]) == 0
    assert '"transitive": true' in capsys.readouterr().out


def test_the_exception_banner_shows_a_countdown_for_discretionary_entries():
    stream = io.StringIO()
    when = (date.today() + timedelta(days=7)).isoformat()
    entry = Exception_("pypi", "x", "1.0.0", "held", "discretionary", expires=when)
    report.exceptions_block([entry], {}, stream=stream)
    assert "expires in 7 days" in stream.getvalue()


def test_a_cleared_transitive_entry_says_so():
    stream = io.StringIO()
    entry = Exception_("pub", "http", "1.5.0", "held", "transitive:x@1.0.0")
    report.exceptions_block([entry], {"pub:http": False}, stream=stream)
    assert "CLEARED" in stream.getvalue()


def test_a_malformed_expiry_degrades_the_banner_instead_of_crashing():
    stream = io.StringIO()
    entry = Exception_("pypi", "x", "1.0.0", "held", "discretionary",
                       expires="whenever")
    report.exceptions_block([entry], {}, stream=stream)
    assert "expires" in stream.getvalue()
    assert report.machine_lines([entry]) == [
        "[DEP-EXCEPTION] pypi:x 1.0.0 expires whenever"
    ]


def test_a_finding_outside_the_repo_root_prints_its_full_path():
    stream = io.StringIO()
    dep = Dep(ecosystem="pub", name="http", constraint="1.5.0",
              path=Path("/elsewhere/pubspec.yaml"), line=0, pinned="1.5.0")
    report.violations([Finding(dep, Severity.STALE, "1.6.0")], Path("/repo"),
                      stream=stream)
    assert "/elsewhere/pubspec.yaml" in stream.getvalue()


def test_the_degraded_banner_lists_at_most_five_reasons():
    stream = io.StringIO()
    report.degraded([f"reason {i}" for i in range(9)], stream=stream)
    body = stream.getvalue()
    assert "9 lookup(s)" in body
    assert "reason 5" not in body


def test_prefetch_with_nothing_to_fetch_is_a_no_op(cache_dir):
    resolver = resolve.Resolver()
    resolver.prefetch([])
    assert resolver.degraded == []


def test_offline_from_the_resolver_is_recorded_not_raised(cache_dir, monkeypatch):
    monkeypatch.setattr("dep_freshness.resolve._fetch", _boom)
    resolver = resolve.Resolver()
    resolver.prefetch([Dep(ecosystem="pub", name="http", constraint="1.0.0",
                           path=Path("pubspec.yaml"), line=1, pinned="1.0.0")])
    assert resolver.degraded


def _boom(*_args):
    raise Offline("down")


def test_a_cache_file_holding_a_json_list_reads_as_a_cold_cache(cache_dir):
    from dep_freshness.cache import Cache
    path = cache_dir / "registry.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert Cache(path).get("pub", "http") is None


def test_a_requirement_line_that_is_not_a_requirement_is_skipped():
    from dep_freshness.parsers.python import _split
    assert _split("!!! nonsense") is None


def test_a_pyproject_with_no_project_table_yields_nothing(tmp_path):
    from dep_freshness.parsers.python import parse_pyproject
    path = write(tmp_path, "pyproject.toml", '[tool.ruff]\nline-length = 88\n')
    assert parse_pyproject(path) == []


def test_a_non_string_requires_python_is_ignored(tmp_path):
    from dep_freshness.parsers.python import parse_pyproject
    path = write(tmp_path, "pyproject.toml",
                 '[project]\nrequires-python = 3\ndependencies = []\n')
    assert parse_pyproject(path) == []


def test_a_group_entry_that_is_not_a_requirement_is_skipped(tmp_path):
    from dep_freshness.parsers.python import parse_pyproject
    path = write(tmp_path, "pyproject.toml",
                 '[dependency-groups]\nlint = ["-r other.txt", "ruff==0.16.5"]\n')
    assert [d.name for d in parse_pyproject(path)] == ["ruff"]


def test_a_lock_entry_without_a_version_is_skipped(tmp_path):
    from dep_freshness.parsers.pubspec import locked_versions
    path = write(tmp_path, "pubspec.lock",
                 "packages:\n  a:\n    version: \"1.0.0\"\n  b:\n    source: sdk\n")
    assert locked_versions(path) == {"a": "1.0.0"}


def test_a_finding_with_no_detail_prints_only_its_headline():
    stream = io.StringIO()
    dep = Dep(ecosystem="pub", name="http", constraint="1.5.0",
              path=Path("pubspec.yaml"), line=4, pinned="1.5.0")
    report.violations([Finding(dep, Severity.STALE, "1.6.0")], Path("."),
                      stream=stream)
    body = stream.getvalue()
    assert "pubspec.yaml:4" in body
    assert "        " not in body.replace("    pub:http", "")


def test_a_finding_with_a_detail_prints_it_indented():
    stream = io.StringIO()
    dep = Dep(ecosystem="pub", name="http", constraint="^1.5.0",
              path=Path("pubspec.yaml"), line=4)
    report.violations(
        [Finding(dep, Severity.UNPINNED, "1.6.0", detail="exact-pin it")],
        Path("."), stream=stream,
    )
    assert "        exact-pin it" in stream.getvalue()


def test_newest_stable_skips_a_candidate_it_cannot_parse():
    assert newest_stable(["1.0.0", "not-a-version"]) == "1.0.0"




def test_newest_stable_skips_a_stable_looking_string_that_is_not_a_version():
    assert newest_stable(["1.0.0", "stable"]) == "1.0.0"


def test_the_module_entrypoint_returns_the_gate_exit_code(
    repo, monkeypatch, cache_dir
):
    """`python3 -m dep_freshness` is what the shell wrapper actually runs."""
    import runpy
    import sys

    write(repo, "pubspec.yaml", "name: d\ndependencies:\n  http: 1.5.0\n")
    monkeypatch.chdir(repo)
    monkeypatch.setattr(sys, "argv", ["dep_freshness", "--all", "--offline"])
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("dep_freshness", run_name="__main__")
    assert exit_info.value.code == 0  # offline + cold cache degrades, never blocks
