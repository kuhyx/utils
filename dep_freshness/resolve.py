"""Turn a `Dep` into "what is the newest stable of this?", via cache then net.

The cache is consulted first, the network second, and an *expired* cache entry
third — that last fallback is what lets a pre-commit run succeed offline
instead of cornering the user, since `--no-verify` is banned.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from dep_freshness._tables import (
    CARGO, GITTAG, GOMOD, MAX_WORKERS, NPM, PUB, PYPI, TOOLCHAIN,
)
from dep_freshness.cache import Cache
from dep_freshness.models import Dep
from dep_freshness.registries import cargo, gittag, gomod, npmjs, pub, pypi
from dep_freshness.registries import toolchain as tc
from dep_freshness.registries.http import Offline

_LOOKUP = {
    PUB: pub.latest,
    PYPI: pypi.latest,
    NPM: npmjs.latest,
    CARGO: cargo.latest,
    GOMOD: gomod.latest,
    GITTAG: gittag.latest,
}


@dataclass
class Answer:
    """Latest stable for one package, and how confident we are in it."""

    version: str | None
    stale_cache_days: float | None = None   # served from an expired entry
    unavailable: bool = False               # no network and no cache at all


def _toolchain_latest(name: str) -> str | None:
    if name == "flutter":
        return tc.flutter_latest()[0]
    if name == "dart":
        return tc.flutter_latest()[1]
    if name == "node":
        return tc.node_latest()
    if name == "python":
        return tc.python_installed()
    return None


def never_cached(ecosystem: str, name: str) -> bool:
    """True for answers that describe THIS process, not a remote registry.

    `toolchain:python` is `platform.python_version()`: free to compute, and
    different on every machine. Caching it made screen-locker's CI red on
    2026-08-28 -- the `actions/cache` restore-key handed a job running 3.14.7
    a 3.13.15 answer written by an older runner image, and the gate declared
    the repo's own `requires-python = ">=3.14"` to exclude "latest".
    """
    return ecosystem == TOOLCHAIN and name == "python"


def _fetch(ecosystem: str, package: str) -> str | None:
    if ecosystem == TOOLCHAIN:
        return _toolchain_latest(package)
    handler = _LOOKUP.get(ecosystem)
    return handler(package) if handler else None


class Resolver:
    """Batch version lookups behind one shared on-disk cache."""

    def __init__(self, cache: Cache | None = None, refresh: bool = False) -> None:
        self.cache = cache if cache is not None else Cache()
        if refresh:
            self.cache.clear()
        self.degraded: list[str] = []

    def prefetch(self, deps: list[Dep]) -> None:
        """Warm the cache for everything not already fresh, eight at a time."""
        wanted = {
            (d.ecosystem, d.name)
            for d in deps
            if not never_cached(d.ecosystem, d.name)
            and (
                not (entry := self.cache.get(d.ecosystem, d.name))
                or not entry.fresh(d.ecosystem)
            )
        }
        if not wanted:
            return
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {
                pool.submit(_fetch, eco, name): (eco, name) for eco, name in wanted
            }
            for future, (eco, name) in futures.items():
                try:
                    self.cache.put(eco, name, future.result())
                except Offline as exc:
                    self.degraded.append(str(exc))
                except Exception as exc:
                    # Deliberately broad: one malformed registry payload
                    # must degrade that single package, not abort a run
                    # spanning ~900 lookups.
                    self.degraded.append(f"{eco}:{name}: {exc}")
        self.cache.save()

    def latest(self, dep: Dep) -> Answer:
        if never_cached(dep.ecosystem, dep.name):
            return Answer(_fetch(dep.ecosystem, dep.name))
        entry = self.cache.get(dep.ecosystem, dep.name)
        if entry and entry.fresh(dep.ecosystem):
            return Answer(entry.version)
        try:
            version = _fetch(dep.ecosystem, dep.name)
        except Offline:
            version = None
        else:
            self.cache.put(dep.ecosystem, dep.name, version)
            return Answer(version)
        if entry is not None:
            return Answer(entry.version, stale_cache_days=entry.age() / 86400)
        return Answer(None, unavailable=True)
