# Copyright (c) 2026 Krzysztof Rudnicki
"""The spool writer behind ``gatelock.error_report``: reports and timed waits.

``Reporter`` writes one JSON line per report to
``$XDG_STATE_HOME/app-errors-spool/<app>.jsonl`` (utils DOCS-app-errors.md),
deduplicating identical errors within ``WINDOW`` seconds and capping each
minute, and never raises into the app it watches. ``SlowWait`` is one timed
wait: written when it outlasts the threshold, or while it is still going.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import datetime as dt
import json
import logging
import os
from pathlib import Path
import threading
import time
import traceback
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from types import TracebackType

#: The kind the board files as "bring this wait under 1 s".
SLOW_KIND = "perf.slow"
#: Seconds in the rate cap's window.
_MINUTE = 60.0

_logger = logging.getLogger(__name__)


def _default_spool() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "app-errors-spool"


def _short(path: str, mark: str) -> str:
    """Return ``path`` from the package that holds it: no home directory in a report."""
    for anchor in ("site-packages/", "dist-packages/"):
        if anchor in path:
            return path.rsplit(anchor, 1)[1]
    if mark in path:
        return mark + path.rsplit(mark, 1)[1]
    return Path(path).name


#: What a report may fail with (a bad spool path, an error whose str() throws):
#: logged and dropped, never raised into the app being watched.
_REPORT_FAILURES = (OSError, ValueError, TypeError, RuntimeError, AttributeError)


@dataclass
class _Guard:
    """A reporter's loop guards: recent errors, minute buckets, re-entry."""

    seen: dict[str, float] = field(default_factory=dict)
    minutes: dict[str, tuple[float, int]] = field(default_factory=dict)
    busy: bool = False
    serial: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)


@dataclass
class Reporter:
    """Writes one app's error and slow-wait reports to the spool."""

    #: Seconds an identical error stays suppressed.
    WINDOW = 30.0
    #: Most error reports written per minute.
    MAX_PER_MINUTE = 20
    #: Most slow-wait reports written per minute.
    MAX_SLOW_PER_MINUTE = 30

    app: str
    repo: str
    mark: str = ""
    spool: Path = field(default_factory=_default_spool)
    build: int = 0
    version: str | None = None
    threshold: float = 1.0
    still_after: float = 5.0
    #: Wall time: entry timestamps, ids and the rate-limit minutes.
    clock: Callable[[], float] = time.time
    #: Elapsed time for waits. Never the wall clock: chrony stepped it 1.33 s
    #: into a fresh lock on 2026-11-25 and that read as a 1.5 s freeze.
    monotonic: Callable[[], float] = time.monotonic
    _guard: _Guard = field(default_factory=_Guard)

    def __post_init__(self) -> None:
        """Default the frame mark to the app's module directory."""
        self.mark = self.mark or self.app.replace("-", "_") + "/"

    def _allowed(self, bucket: str, cap: int) -> bool:
        now = self.clock()
        start, count = self._guard.minutes.get(bucket, (now, 0))
        if now - start >= _MINUTE:
            start, count = now, 0
        if count >= cap:
            return False
        self._guard.minutes[bucket] = (start, count + 1)
        return True

    def _write(self, entry: dict[str, object]) -> None:
        at = dt.datetime.fromtimestamp(self.clock(), dt.UTC)
        entry |= {
            "at": at.strftime("%Y-%m-%dT%H:%M:%S.") + f"{at.microsecond // 1000:03d}Z",
            "repo": self.repo,
            "mark": self.mark,
            "build": self.build,
        }
        if self.version:
            entry["version"] = self.version
        line = json.dumps(entry, sort_keys=True) + "\n"
        with self._guard.lock:
            self.spool.mkdir(parents=True, exist_ok=True)
            with (self.spool / f"{self.app}.jsonl").open("a", encoding="utf-8") as f:
                f.write(line)

    def report(self, kind: str, error: object, tb: TracebackType | None = None) -> None:
        """Record ``error`` (exception or message) as ``kind``, unless suppressed."""
        if self._guard.busy:
            return
        self._guard.busy = True
        try:
            text = (
                f"{type(error).__name__}: {error}"
                if isinstance(error, BaseException)
                else str(error)
            )
            now = self.clock()
            key = f"{kind}|{text}"
            self._guard.seen = {
                k: t for k, t in self._guard.seen.items() if now - t < self.WINDOW
            }
            if key in self._guard.seen or not self._allowed(
                "error", self.MAX_PER_MINUTE
            ):
                return
            self._guard.seen[key] = now
            frames = traceback.extract_tb(tb) if tb is not None else []
            stack = [
                f"{_short(f.filename, self.mark)}:{f.lineno} in {f.name}"
                for f in reversed(frames)
            ]
            self._write({"kind": kind, "error": text, "stack": stack})
        except _REPORT_FAILURES:
            # Never raise into the app it watches; the log keeps the why.
            _logger.exception("app-errors: report not written")
        finally:
            self._guard.busy = False

    def slow(
        self,
        operation: str,
        ms: int,
        *,
        wait_id: str,
        route: str | None = None,
        still: bool = False,
    ) -> None:
        """Record one wait of ``ms`` milliseconds on ``operation``."""
        try:
            if not self._allowed("slow", self.MAX_SLOW_PER_MINUTE):
                return
            entry: dict[str, object] = {
                "kind": SLOW_KIND,
                "error": f"{operation} waited {ms} ms",
                "operation": operation,
                "durationMs": ms,
                "waitId": wait_id,
                "still": still,
            }
            if route:
                entry["route"] = route
            self._write(entry)
        except _REPORT_FAILURES:
            _logger.exception("app-errors: slow wait not written")

    def begin(self, operation: str, *, route: str | None = None) -> SlowWait:
        """Start timing a wait on ``operation`` (``coach.load``); ``end`` it after."""
        self._guard.serial += 1
        return SlowWait(
            self,
            operation,
            route,
            self.monotonic(),
            f"{int(self.clock() * 1000):x}-{self._guard.serial}",
        )

    @contextmanager
    def wait(self, operation: str, *, route: str | None = None) -> Iterator[SlowWait]:
        """Time the ``with`` block as a wait on ``operation``."""
        handle = self.begin(operation, route=route)
        try:
            yield handle
        finally:
            handle.end()


@dataclass
class SlowWait:
    """One timed wait: reported when it ends after the threshold, or is still going."""

    reporter: Reporter
    operation: str
    route: str | None
    started: float
    id: str
    _ended: bool = False
    _reported_still: bool = False
    _timer: threading.Timer = field(init=False)

    def __post_init__(self) -> None:
        """Arm the still-waiting report (a hung load never ends)."""
        self._timer = threading.Timer(self.reporter.still_after, self._still)
        self._timer.daemon = True
        self._timer.start()

    def _ms(self) -> int:
        return round((self.reporter.monotonic() - self.started) * 1000)

    def _still(self) -> None:
        if self._ended:
            return
        self._reported_still = True
        self.reporter.slow(
            self.operation, self._ms(), wait_id=self.id, route=self.route, still=True
        )

    def end(self) -> None:
        """End the wait; write it if it outlasted the threshold; repeats do nothing."""
        if self._ended:
            return
        self._ended = True
        self._timer.cancel()
        ms = self._ms()
        if self._reported_still or ms > self.reporter.threshold * 1000:
            self.reporter.slow(self.operation, ms, wait_id=self.id, route=self.route)
