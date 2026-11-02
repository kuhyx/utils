"""The one paced serial lane both transports feed (DOCS-coach-relay.md 1).

FIFO by arrival; one request runs at a time and none overtakes an earlier
one. At most one request *starts* every `pace_s` (3 s), globally across the
desktop and the phone; the rest wait. A request arriving while `max_queued`
(5) already wait is answered ``rate_limited`` and never runs.

Every result goes into the done-map before any listener hears of it, so a
client that resends a rid is re-answered, never re-run.
"""

from __future__ import annotations

from collections import deque
import logging
import threading
import time
from typing import TYPE_CHECKING, Any, Final

from leetcode_coach.relay import protocol

if TYPE_CHECKING:
    from collections.abc import Callable

    from leetcode_coach.relay.done import DoneMap

_logger: Final = logging.getLogger(__name__)

PACE_S: Final = 3.0
MAX_QUEUED: Final = 5


class Lane:  # pylint: disable=too-many-instance-attributes
    """Queue, pacing and the worker loop around one request handler."""

    def __init__(  # pylint: disable=too-many-arguments
        self,
        handle: Callable[[protocol.Request], dict[str, Any]],
        done: DoneMap,
        *,
        clock_ms: Callable[[], int],
        monotonic: Callable[[], float] = time.monotonic,
        pace_s: float = PACE_S,
        max_queued: int = MAX_QUEUED,
    ) -> None:
        """Bind the handler; nothing runs until `run`."""
        self._handle = handle
        self.done = done
        self._clock = clock_ms
        self._monotonic = monotonic
        self._pace = pace_s
        self._max = max_queued
        self._cv = threading.Condition()
        self._queue: deque[protocol.Request] = deque()
        self._last_start = float("-inf")
        self.busy: str | None = None
        self.on_result: list[Callable[[protocol.Request, dict[str, Any]], None]] = []
        self.on_busy: list[Callable[[str | None], None]] = []

    def now(self) -> int:
        """Unix ms, by the relay's clock."""
        return self._clock()

    def known(self, rid: str) -> bool:
        """Whether `rid` is queued, running or finished."""
        with self._cv:
            waiting = rid == self.busy or any(r.rid == rid for r in self._queue)
        return waiting or self.done.get(rid) is not None

    def result(self, rid: str) -> dict[str, Any] | None:
        """The finished result of `rid`, or None while it waits or runs."""
        done = self.done.get(rid)
        return None if done is None else done.result

    def finish(self, rid: str, transport: str, result: dict[str, Any]) -> None:
        """Store a result that never ran (``bad_request``, ``rate_limited``)."""
        self.done.put(rid, transport, result)

    def submit(self, req: protocol.Request) -> dict[str, Any] | None:
        """Queue `req`; its result now if it is already known, else None."""
        if (done := self.done.get(req.rid)) is not None:
            return done.result
        with self._cv:
            if req.rid == self.busy or any(r.rid == req.rid for r in self._queue):
                return None
            if len(self._queue) >= self._max:
                wait_ms = int(self._pace * 1000 * len(self._queue))
                result = protocol.failure(
                    "rate_limited",
                    "The PC is busy with earlier requests; send again shortly.",
                    at=self._clock(),
                    retry=True,
                    retry_after_ms=wait_ms,
                )
                self.finish(req.rid, req.transport, result)
                return result
            self._queue.append(req)
            self._cv.notify_all()
        return None

    def _next(self, stop: threading.Event) -> protocol.Request | None:
        """The next request once its start slot has come; None when stopping."""
        with self._cv:
            while not stop.is_set():
                if not self._queue:
                    self._cv.wait(0.5)
                    continue
                delay = self._last_start + self._pace - self._monotonic()
                if delay > 0:
                    self._cv.wait(delay)
                    continue
                self._last_start = self._monotonic()
                req = self._queue.popleft()
                self.busy = req.rid
                return req
        return None

    def _run_one(self, req: protocol.Request) -> dict[str, Any]:
        try:
            return self._handle(req)
        except Exception:  # pylint: disable=broad-exception-caught
            # The traceback goes to the journal only; kuhy sees one line.
            _logger.exception("request %s (%s) crashed", req.rid, req.kind)
            return protocol.failure(
                "worker_error",
                "The coach hit an internal error; see the relay's journal.",
                at=self._clock(),
            )

    def _tell(self, busy: str | None) -> None:
        for listener in self.on_busy:
            listener(busy)

    def run(self, stop: threading.Event) -> None:
        """Run requests until `stop`; a request already running finishes."""
        while (req := self._next(stop)) is not None:
            self._tell(req.rid)
            result = self._run_one(req)
            self.done.put(req.rid, req.transport, result)
            with self._cv:
                self.busy = None
            self._tell(None)
            for listener in self.on_result:
                listener(req, result)

    def stop(self) -> None:
        """Wake the worker so it notices its stop event at once."""
        with self._cv:
            self._cv.notify_all()
