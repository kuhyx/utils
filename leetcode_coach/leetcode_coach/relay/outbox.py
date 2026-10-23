"""The phone mirror's writes, in order, on their own thread.

A hanging Firebase must never stall the desktop: the lane's one worker only
*enqueues* (chat lines, ``state``, the heartbeat, a result) and this outbox
writes them. Order is the contract's: chat reset / new lines, then
``state``, then the heartbeat, then the request's result -- the phone
refetches chat when ``heartbeat.state_rev`` moves, so a heartbeat landing
before its chat lines would lose one. ``state`` and the heartbeat keep only
their latest value (an older one still waiting is dropped, the newer goes to
the back); results and chat lines are never dropped. A failed write stays at
the front and is retried after a backoff; nothing behind it overtakes it.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import logging
import threading
from typing import TYPE_CHECKING, Final

from leetcode_coach.relay.rtdb import RtdbError

if TYPE_CHECKING:
    from collections.abc import Callable

_logger: Final = logging.getLogger(__name__)

BACKOFF_S: Final = (1.0, 2.0, 5.0, 10.0, 30.0)
IDLE_S: Final = 0.5


@dataclass(frozen=True)
class Write:
    """One pending write: what it is (for the log) and how to do it."""

    what: str
    run: Callable[[], None]
    latest: str | None = None
    """A key whose older pending writes this one replaces (state, heartbeat)."""


class Outbox:
    """An ordered queue of RTDB writes and the loop that drains it."""

    def __init__(self) -> None:
        """Start empty; `run` drains on a thread, `drain` in the caller."""
        self._cv = threading.Condition()
        self._writes: deque[Write] = deque()

    def put(
        self, what: str, run: Callable[[], None], latest: str | None = None
    ) -> None:
        """Queue one write (replacing a waiting one with the same `latest`)."""
        with self._cv:
            if latest is not None:
                self._writes = deque(w for w in self._writes if w.latest != latest)
            self._writes.append(Write(what, run, latest))
            self._cv.notify_all()

    def pending(self) -> list[str]:
        """What is still waiting, in order."""
        with self._cv:
            return [w.what for w in self._writes]

    def drain(self) -> bool:
        """Write everything waiting; False at the first failure (it stays first)."""
        while True:
            with self._cv:
                if not self._writes:
                    return True
                write = self._writes.popleft()
            try:
                write.run()
            except RtdbError as exc:
                _logger.warning("RTDB %s failed: %s", write.what, exc)
                with self._cv:
                    newer = write.latest is not None and any(
                        w.latest == write.latest for w in self._writes
                    )
                    if not newer:
                        self._writes.appendleft(write)
                return False

    def run(
        self, stop: threading.Event, wait: Callable[[float], object] | None = None
    ) -> None:
        """Drain until `stop`, backing off after a failed write."""
        pause = stop.wait if wait is None else wait
        failures = 0
        while not stop.is_set():
            with self._cv:
                if not self._writes:
                    self._cv.wait(IDLE_S)
                    continue
            if self.drain():
                failures = 0
                continue
            pause(BACKOFF_S[min(failures, len(BACKOFF_S) - 1)])
            failures += 1

    def wake(self) -> None:
        """Let a waiting `run` notice its stop event at once."""
        with self._cv:
            self._cv.notify_all()
