"""Cache-then-network-then-stale-cache, and the toolchain routing.

The third step is the one that matters: serving an *expired* entry when the
network is gone is what keeps the pre-commit hook from cornering a user who is
forbidden from passing `--no-verify`.
"""

from __future__ import annotations

from pathlib import Path
import time

import pytest

from dep_freshness.cache import Cache, Entry, ttl_for
from dep_freshness.models import Dep
from dep_freshness.registries import http
from dep_freshness.registries import toolchain as tc
from dep_freshness.resolve import Resolver, _toolchain_latest


def dep(ecosystem="pub", name="http") -> Dep:
    return Dep(ecosystem=ecosystem, name=name, constraint="1.0.0",
               path=Path("pubspec.yaml"), line=1, pinned="1.0.0")


@pytest.fixture
def resolver(cache_dir):
    return Resolver(cache=Cache(cache_dir / "registry.json"))


def test_a_fresh_cache_entry_short_circuits_the_network(resolver, monkeypatch):
    resolver.cache.put("pub", "http", "1.6.0")
    monkeypatch.setattr("dep_freshness.resolve._fetch", _explode)
    assert resolver.latest(dep()).version == "1.6.0"


def test_a_cold_cache_fetches_and_stores(resolver, monkeypatch):
    monkeypatch.setattr("dep_freshness.resolve._fetch", lambda *_a: "1.6.0")
    assert resolver.latest(dep()).version == "1.6.0"
    assert resolver.cache.get("pub", "http").version == "1.6.0"


def test_an_expired_entry_is_served_when_the_network_is_gone(resolver, monkeypatch):
    resolver.cache.put("pub", "http", "1.6.0")
    stale = time.time() - ttl_for("pub") - 60
    resolver.cache._data["pub/http"]["fetched_at"] = stale
    monkeypatch.setattr("dep_freshness.resolve._fetch", _offline)
    answer = resolver.latest(dep())
    assert answer.version == "1.6.0"
    assert answer.stale_cache_days is not None
    assert not answer.unavailable


def test_no_cache_and_no_network_is_unavailable(resolver, monkeypatch):
    monkeypatch.setattr("dep_freshness.resolve._fetch", _offline)
    assert resolver.latest(dep()).unavailable


def test_prefetch_records_why_a_lookup_degraded(resolver, monkeypatch):
    monkeypatch.setattr("dep_freshness.resolve._fetch", _offline)
    resolver.prefetch([dep()])
    assert resolver.degraded


def test_prefetch_survives_an_unexpected_error(resolver, monkeypatch):
    monkeypatch.setattr("dep_freshness.resolve._fetch", _explode)
    resolver.prefetch([dep()])
    assert any("boom" in reason for reason in resolver.degraded)


def test_prefetch_skips_packages_already_fresh(resolver, monkeypatch):
    resolver.cache.put("pub", "http", "1.6.0")
    monkeypatch.setattr("dep_freshness.resolve._fetch", _explode)
    resolver.prefetch([dep()])
    assert resolver.degraded == []


def test_refresh_discards_the_existing_cache(cache_dir, monkeypatch):
    seeded = Cache(cache_dir / "registry.json")
    seeded.put("pub", "http", "1.5.0")
    seeded.save()
    monkeypatch.setattr("dep_freshness.resolve._fetch", lambda *_a: "1.6.0")
    resolver = Resolver(cache=Cache(cache_dir / "registry.json"), refresh=True)
    assert resolver.latest(dep()).version == "1.6.0"


def test_the_python_target_ignores_the_cache_entirely(resolver, monkeypatch):
    """screen-locker went red on a cached interpreter from another machine.

    `actions/cache` restored a `dep-freshness-` entry written by an older
    runner image, so a job that `setup-python` had put on 3.14.7 was told the
    "current toolchain" was 3.13.15 -- and the repo's own
    `requires-python = ">=3.14"` was reported as excluding latest. The answer
    describes this process and costs nothing, so it is never cached.
    """
    resolver.cache.put("toolchain", "python", "3.13.15")
    monkeypatch.setattr(tc, "python_installed", lambda: "3.14.7")
    assert resolver.latest(dep("toolchain", "python")).version == "3.14.7"


def test_prefetch_does_not_warm_the_python_target(resolver, monkeypatch):
    monkeypatch.setattr(
        http, "get_json", lambda *a, **k: pytest.fail("no lookup is needed")
    )
    monkeypatch.setattr(
        tc, "python_installed", lambda: pytest.fail("prefetch must skip python")
    )
    resolver.prefetch([dep("toolchain", "python")])


def test_git_tags_get_a_longer_ttl_than_registries():
    assert ttl_for("gittag") > ttl_for("pub")


def test_a_corrupt_cache_file_reads_as_a_cold_cache(cache_dir):
    path = cache_dir / "registry.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    assert Cache(path).get("pub", "http") is None


def test_a_malformed_cache_entry_is_ignored(cache_dir):
    cache = Cache(cache_dir / "registry.json")
    cache._data["pub/http"] = {"version": "1.6.0"}  # no fetched_at
    assert cache.get("pub", "http") is None


def test_saving_is_a_no_op_when_nothing_changed(cache_dir):
    cache = Cache(cache_dir / "registry.json")
    cache.save()
    assert not (cache_dir / "registry.json").exists()


def test_an_unwritable_cache_slows_the_next_run_but_does_not_fail_it(tmp_path):
    blocked = tmp_path / "afile"
    blocked.write_text("x", encoding="utf-8")
    cache = Cache(blocked / "registry.json")
    cache.put("pub", "http", "1.6.0")
    cache.save()  # must not raise


def test_entry_age_is_measured_from_fetch_time():
    assert Entry("1.0.0", time.time() - 120).age() >= 120


@pytest.mark.parametrize("name,expected", [
    ("flutter", "3.47.2"), ("dart", "3.13.2"), ("node", "24.20.0"),
])
def test_toolchain_routing(monkeypatch, name, expected):
    monkeypatch.setattr(tc, "flutter_latest", lambda: ("3.47.2", "3.13.2"))
    monkeypatch.setattr(tc, "node_latest", lambda: "24.20.0")
    assert _toolchain_latest(name) == expected


def test_python_targets_the_installed_interpreter():
    """Never python.org: on Arch the interpreter is pacman-managed."""
    import platform
    assert _toolchain_latest("python") == platform.python_version()


def test_an_unknown_toolchain_has_no_target():
    assert _toolchain_latest("go") is None


def _offline(*_args):
    raise http.Offline("no network")


def _explode(*_args):
    raise RuntimeError("boom")
