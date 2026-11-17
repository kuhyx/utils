# Copyright (c) 2026 Krzysztof Rudnicki
"""Report every error and every wait over 1 s of a Tk (or any Python) app.

The Python reporter of kuhy's shared app-errors pipeline (utils
``DOCS-app-errors.md``; the Dart one is crdt_sync_flutter's, generalised from
kartka). ``install`` once at start-up hooks ``sys.excepthook``,
``threading.excepthook`` and Tk callback errors (``Misc._report_exception``,
which every root, ``GateRoot`` included, goes through), each chained to the
hook it replaces. ``Reporter.begin``/``wait`` time a user-visible wait, and
``watch_stalls`` reports a frozen Tk loop with no call-site work.

A report is one JSON line in ``$XDG_STATE_HOME/app-errors-spool/<app>.jsonl``.
The PC's ``app-errors`` ingest (utils ``app_errors/``) reads it, groups it by
signature and hands it to the board, which files a ticket. Reporting shows
nothing on screen, never raises and never reports from inside a report.
Identical errors within ``WINDOW`` seconds are dropped and at most
``MAX_PER_MINUTE`` are written per minute (an error loop cannot fill the disk).
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import datetime as dt
import json
import os
from pathlib import Path
import sys
import threading
import time
import tkinter as tk
import traceback
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from types import TracebackType

#: The kind the board files as "bring this wait under 1 s".
SLOW_KIND = "perf.slow"
#: How often the stall watch ticks, milliseconds.
STALL_TICK_MS = 100

_TK_DOOR = "_report_exception"

_installed: Reporter | None = None


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
    clock: Callable[[], float] = time.time
    _seen: dict[str, float] = field(default_factory=dict)
    _minutes: dict[str, tuple[float, int]] = field(default_factory=dict)
    _busy: bool = False
    _serial: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        """Default the frame mark to the app's module directory."""
        self.mark = self.mark or self.app.replace("-", "_") + "/"

    def _allowed(self, bucket: str, cap: int) -> bool:
        now = self.clock()
        start, count = self._minutes.get(bucket, (now, 0))
        if now - start >= 60:  # noqa: PLR2004 -- one minute
            start, count = now, 0
        if count >= cap:
            return False
        self._minutes[bucket] = (start, count + 1)
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
        with self._lock:
            self.spool.mkdir(parents=True, exist_ok=True)
            with (self.spool / f"{self.app}.jsonl").open("a", encoding="utf-8") as f:
                f.write(line)

    def report(self, kind: str, error: object, tb: TracebackType | None = None) -> None:
        """Record ``error`` (exception or message) as ``kind``, unless suppressed."""
        if self._busy:
            return
        self._busy = True
        try:
            text = (
                f"{type(error).__name__}: {error}"
                if isinstance(error, BaseException)
                else str(error)
            )
            now = self.clock()
            key = f"{kind}|{text}"
            self._seen = {k: t for k, t in self._seen.items() if now - t < self.WINDOW}
            if key in self._seen or not self._allowed("error", self.MAX_PER_MINUTE):
                return
            self._seen[key] = now
            frames = traceback.extract_tb(tb) if tb is not None else []
            stack = [
                f"{_short(f.filename, self.mark)}:{f.lineno} in {f.name}"
                for f in reversed(frames)
            ]
            self._write({"kind": kind, "error": text, "stack": stack})
        except Exception:  # noqa: BLE001, S110 -- never raise into the app it watches
            pass
        finally:
            self._busy = False

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
        except Exception:  # noqa: BLE001, S110 -- never raise into the app
            pass

    def begin(self, operation: str, *, route: str | None = None) -> SlowWait:
        """Start timing a wait on ``operation`` (``coach.load``); ``end`` it after."""
        self._serial += 1
        return SlowWait(
            self,
            operation,
            route,
            self.clock(),
            f"{int(self.clock() * 1000):x}-{self._serial}",
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
        return round((self.reporter.clock() - self.started) * 1000)

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


def watch_stalls(root: tk.Misc, reporter: Reporter) -> None:
    """Report each time ``root``'s event loop froze past the threshold.

    The operation is ``tk.mainloop``: a blocking call on the Tk thread.
    """
    last = [reporter.clock()]

    def tick() -> None:
        now = reporter.clock()
        late = round((now - last[0]) * 1000) - STALL_TICK_MS
        last[0] = now
        if late > reporter.threshold * 1000:
            reporter.slow("tk.mainloop", late, wait_id=f"stall-{int(now * 1000):x}")
        try:
            root.after(STALL_TICK_MS, tick)
        except tk.TclError:
            return  # the window is gone

    root.after(STALL_TICK_MS, tick)


def install(
    app: str,
    repo: str,
    *,
    mark: str = "",
    build: int = 0,
    version: str | None = None,
) -> Reporter:
    """Hook uncaught, thread and Tk callback errors once; return the reporter.

    The spool is ``$XDG_STATE_HOME/app-errors-spool``; tests build a
    ``Reporter`` with their own ``spool`` instead.
    """
    global _installed  # noqa: PLW0603 -- one set of process-wide hooks
    if _installed is not None:
        return _installed
    rep = Reporter(
        app=app,
        repo=repo,
        mark=mark,
        build=build,
        version=version,
    )
    prior_sys = sys.excepthook

    def sys_hook(
        kind: type[BaseException], value: BaseException, tb: TracebackType | None
    ) -> None:
        rep.report("uncaught.python", value, tb)
        prior_sys(kind, value, tb)

    prior_thread = threading.excepthook

    def thread_hook(args: threading.ExceptHookArgs) -> None:
        value: object = args.exc_value
        if value is None:
            value = args.exc_type.__name__
        rep.report("uncaught.thread", value, args.exc_traceback)
        prior_thread(args)

    # Misc._report_exception is the one door every Tk callback error passes,
    # whatever root subclass overrides report_callback_exception.
    prior_tk: Callable[[tk.Misc], None] = getattr(tk.Misc, _TK_DOOR)

    def tk_hook(widget: tk.Misc) -> None:
        _, value, tb = sys.exc_info()
        if value is not None:
            rep.report("uncaught.tk", value, tb)
        prior_tk(widget)

    sys.excepthook = sys_hook
    threading.excepthook = thread_hook
    setattr(tk.Misc, _TK_DOOR, tk_hook)
    _installed = rep
    return rep
