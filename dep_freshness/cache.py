"""On-disk snapshot of registry answers, shared across all 78 manifests.

Overlapping dependencies are fetched once per TTL rather than once per repo,
and — the load-bearing part — an *expired* entry is still served when the
network is down. A pre-commit hook that hard-fails offline would corner the
user, because `--no-verify` is banned.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
import time

from dep_freshness._tables import (
    CACHE_FILE,
    CACHE_PATH_ENV,
    DEFAULT_CACHE_DIR,
    GITTAG,
    TTL_GITTAG_SECONDS,
    TTL_SECONDS,
)


def cache_dir() -> Path:
    """Where the snapshot lives; overridable for tests via the env var."""
    raw = os.environ.get(CACHE_PATH_ENV) or DEFAULT_CACHE_DIR
    return Path(raw).expanduser()


def ttl_for(ecosystem: str) -> int:
    """Git tags move rarely and cost a subprocess, so they cache longer."""
    return TTL_GITTAG_SECONDS if ecosystem == GITTAG else TTL_SECONDS


@dataclass
class Entry:
    """One cached lookup, plus how old it is."""

    version: str | None
    fetched_at: float

    def age(self, now: float | None = None) -> float:
        return (time.time() if now is None else now) - self.fetched_at

    def fresh(self, ecosystem: str, now: float | None = None) -> bool:
        return self.age(now) < ttl_for(ecosystem)


class Cache:
    """A JSON file keyed `ecosystem/package` -> {version, fetched_at}."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (cache_dir() / CACHE_FILE)
        self._data: dict[str, dict] = {}
        self._dirty = False
        self._load()

    def _load(self) -> None:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return
        try:
            parsed = json.loads(raw)
        except ValueError:
            return  # a corrupt cache is a cold cache, never an error
        if isinstance(parsed, dict):
            self._data = {k: v for k, v in parsed.items() if isinstance(v, dict)}

    @staticmethod
    def key(ecosystem: str, package: str) -> str:
        return f"{ecosystem}/{package}"

    def get(self, ecosystem: str, package: str) -> Entry | None:
        record = self._data.get(self.key(ecosystem, package))
        if record is None:
            return None
        try:
            return Entry(record.get("version"), float(record["fetched_at"]))
        except (KeyError, TypeError, ValueError):
            return None

    def put(self, ecosystem: str, package: str, version: str | None) -> None:
        self._data[self.key(ecosystem, package)] = {
            "version": version,
            "fetched_at": time.time(),
        }
        self._dirty = True

    def clear(self) -> None:
        self._data = {}
        self._dirty = True

    def save(self) -> None:
        """Atomic write; a half-written cache would poison every later run."""
        if not self._dirty:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w", dir=self.path.parent, delete=False, encoding="utf-8"
            ) as handle:
                json.dump(self._data, handle)
                temp = Path(handle.name)
            temp.replace(self.path)
            self._dirty = False
        except OSError:
            pass  # an unwritable cache slows the next run; it must not fail it
