"""`toolchain:python` is a registry answer, never the interpreter running the gate.

kuhyx/spellcode went red on one runner and green on another: `setup-python`
with "3.x" handed one job 3.15.0 and the next 3.14.8, so a `transitive:`
allowlist entry was dead (exit 2) on one machine and required (exit 1) on the
other. The target must not depend on where the gate happens to run.
"""

from __future__ import annotations

import platform
from pathlib import Path

import pytest

from dep_freshness.models import Dep
from dep_freshness.registries import http
from dep_freshness.registries import toolchain as tc
from dep_freshness.resolve import Resolver, _toolchain_latest

# Shaped like python.org's /api/v2/downloads/release/ rows, trimmed.
RELEASES = [
    {"name": "Python 2.7.18", "pre_release": False},
    {"name": "Python 3.14.8", "pre_release": False},
    {"name": "Python 3.15.0", "pre_release": False},
    # The Windows install manager is listed as a "release" with version 100;
    # read naively it is Python 26.4.
    {"name": "Python install manager 26.4", "pre_release": False},
    {"name": "Python 3.16.0a1", "pre_release": True},
    {"name": "Python 3.16.0", "pre_release": True},  # flagged, so not final
]


@pytest.fixture
def feed(monkeypatch):
    def install(payload):
        monkeypatch.setattr(tc, "get_json", lambda *_a, **_k: payload)

    return install


def python_dep() -> Dep:
    return Dep(
        ecosystem="toolchain", name="python", constraint="3.14.8",
        path=Path(".python-version"), line=1,
    )


@pytest.fixture
def no_interpreter(monkeypatch):
    """Any read of the running interpreter's version is a failure."""
    monkeypatch.setattr(
        platform,
        "python_version",
        lambda: pytest.fail("the target must not come from this interpreter"),
    )


@pytest.mark.parametrize("interpreter", ["3.14.8", "3.15.0"])
def test_latest_is_the_same_whatever_interpreter_runs_the_gate(
    feed, monkeypatch, interpreter
):
    feed(RELEASES)
    monkeypatch.setattr(platform, "python_version", lambda: interpreter)
    assert _toolchain_latest("python") == "3.15.0"


def test_the_registry_answer_skips_pre_releases_and_the_install_manager(feed):
    feed(RELEASES)
    assert tc.python_latest() == "3.15.0"


def test_a_missing_feed_is_unknown(feed):
    feed(None)
    assert tc.python_latest() is None


def test_rows_without_a_name_are_ignored(feed):
    feed([{"pre_release": False}, {"name": "Python 3.14.8"}])
    assert tc.python_latest() == "3.14.8"


@pytest.fixture
def resolver(tmp_path):
    from dep_freshness.cache import Cache

    return Resolver(Cache(tmp_path / "registry.json"))


def test_the_answer_is_cached_like_any_registry(resolver, feed, no_interpreter):
    feed(RELEASES)
    resolver.prefetch([python_dep()])
    entry = resolver.cache.get("toolchain", "python")
    assert entry is not None and entry.version == "3.15.0"


def test_offline_serves_the_cached_answer_as_degraded(resolver, no_interpreter):
    resolver.cache.put("toolchain", "python", "3.15.0")
    resolver.cache._data["toolchain/python"]["fetched_at"] = 0.0  # long expired
    http.force_offline()
    answer = resolver.latest(python_dep())
    assert answer.version == "3.15.0"
    assert answer.stale_cache_days is not None


def test_offline_with_no_cache_is_unavailable(resolver, no_interpreter):
    http.force_offline()
    answer = resolver.latest(python_dep())
    assert answer.version is None
    assert answer.unavailable
