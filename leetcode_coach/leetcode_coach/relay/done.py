"""The done-map: every finished rid and its result (DOCS-coach-relay.md 1).

A client that lost the answer sends the SAME rid again, and the relay must
re-answer it, never re-run it: a re-run chat turn would spend a model call
and post a second reply. So every result -- ``bad_request`` and
``rate_limited`` included -- lands here before anyone is told. Kept in
``requests_done.jsonl`` for 30 days, so a relay restart still knows; a
desktop result is forgotten after 24 h (the wrapper polls for seconds).

Appends are one ``os.write`` on an ``O_APPEND`` descriptor, like the session
log. The file is compacted at start-up, when expired lines are dropped.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
import threading
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_logger: Final = logging.getLogger(__name__)

DAY_MS: Final = 24 * 3600 * 1000
KEEP_MS: Final = 30 * DAY_MS
DESKTOP_KEEP_MS: Final = DAY_MS


@dataclass(frozen=True)
class Done:
    """One finished request."""

    rid: str
    at: int
    transport: str
    result: dict[str, Any]


def _parse(line: str) -> Done | None:
    try:
        raw = json.loads(line)
        return Done(
            str(raw["rid"]), int(raw["at"]), str(raw["transport"]), dict(raw["result"])
        )
    except (ValueError, KeyError, TypeError) as exc:
        _logger.warning("done-map line skipped: %s", exc)
        return None


class DoneMap:
    """Finished rids, in memory and on disk."""

    def __init__(self, path: Path, clock_ms: Callable[[], int]) -> None:
        """Load `path`, dropping (and compacting away) expired results."""
        self._path = path
        self._clock = clock_ms
        self._lock = threading.Lock()
        self._done: dict[str, Done] = {}
        lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
        cutoff = clock_ms() - KEEP_MS
        for line in lines:
            done = _parse(line) if line.strip() else None
            if done is not None and done.at >= cutoff:
                self._done[done.rid] = done
        if len(self._done) != len(lines):
            self._rewrite()

    def _line(self, done: Done) -> bytes:
        record = {
            "rid": done.rid,
            "at": done.at,
            "transport": done.transport,
            "result": done.result,
        }
        return (json.dumps(record, ensure_ascii=False) + "\n").encode()

    def _rewrite(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_bytes(b"".join(self._line(d) for d in self._done.values()))
        tmp.replace(self._path)

    def put(self, rid: str, transport: str, result: dict[str, Any]) -> None:
        """Record `rid`'s result (before any client is told about it)."""
        done = Done(rid, self._clock(), transport, result)
        with self._lock:
            self._done[rid] = done
            self._path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self._path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            try:
                os.write(fd, self._line(done))
            finally:
                os.close(fd)

    def get(self, rid: str) -> Done | None:
        """The finished request, unless it expired (24 h for the desktop)."""
        with self._lock:
            done = self._done.get(rid)
        if done is None:
            return None
        keep = DESKTOP_KEEP_MS if done.transport == "desktop" else KEEP_MS
        return done if self._clock() - done.at <= keep else None
