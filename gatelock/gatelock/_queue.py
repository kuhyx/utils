"""Wait our turn instead of fighting for the screen.

The lockers form a ladder (see ``_arbiter.py``'s module docstring: wake up,
then work out, then grind, then eat), but ranking alone does not stop two
apps drawing competing windows at once. Every consumer publishes a claim,
calls ``acquire_holder()``, and used to discard the result and build its
window anyway -- the loser draws a visible, ungrabbed window *behind* the
winner and spins in gatelock's forever-retrying grab loop.

So this waits **headlessly**: no root, no surfaces, nothing on screen, until
no live claim outranks us. Then the caller arms normally.

Two rules it must not break:

* **Never exit because another lock is running.** Standing down permanently
  would turn "start the workout lock" into a way to skip the grind.
* **Never give up and leave the machine unlocked.** The deadline is a runaway
  backstop for a wait that should have ended; reaching it arms anyway and says
  so at ERROR.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import time
from typing import TYPE_CHECKING, Final

_logger: Final = logging.getLogger(__name__)

QUEUE_POLL_SECONDS: Final = 2.0
QUEUE_DEADLINE_SECONDS: Final = 6 * 60 * 60
# How often to re-state a still-blocked wait at WARNING. A long wait used
# to produce exactly one INFO line at the moment it started and nothing
# else until it ended: on 2026-08-30 screen_locker sat behind wake_alarm
# for 2h58m and `systemctl status` showed a healthy, active, silent unit.
QUEUE_HEARTBEAT_SECONDS: Final = 300.0

if TYPE_CHECKING:
    from collections.abc import Callable

    from gatelock._arbiter import Arbiter, Claim


@dataclass(frozen=True)
class QueueResult:
    """How the wait ended."""

    waited_seconds: float
    blocked_by: tuple[str, ...]
    """Apps we queued behind, in the order they were first seen."""

    timed_out: bool
    """``True`` means the deadline was hit and we armed anyway."""

    @property
    def queued(self) -> bool:
        """Whether we actually had to wait for anything."""
        return bool(self.blocked_by)


def stronger_claims(arbiter: Arbiter) -> tuple[Claim, ...]:
    """Live claims that outrank ours.

    Rank alone, deliberately -- not gatelock's strength comparison. We are
    *queueing*, not standing down: a higher-ranked app owns the screen right
    now whether or not it grabs as hard as we would, and drawing over it is
    the behaviour this module exists to remove.
    """
    mine = arbiter.claim.instance_id
    return tuple(
        claim
        for claim in arbiter.live_claims()
        if claim.instance_id != mine and claim.rank > arbiter.claim.rank
    )


@dataclass(frozen=True)
class Timebase:
    """Injected clock and sleep, so a wait can be tested without waiting.

    Bundled rather than passed as two separate arguments: ``wait_for_turn``
    is a public entry point and its knobs are already at the limit ruff
    allows, and these two only ever vary together.
    """

    sleep: Callable[[float], None] = time.sleep
    now: Callable[[], float] = time.monotonic


class _Wait:
    """One in-progress wait: who is ahead of us, and for how long.

    A class rather than closures inside ``wait_for_turn`` because the
    heartbeat needs state that outlives a single loop iteration, and threading
    that through as locals pushed the function past ruff's complexity limit.
    """

    def __init__(
        self,
        arbiter: Arbiter,
        on_state: Callable[[tuple[str, ...], float], None] | None,
        started: float,
    ) -> None:
        """Start tracking a wait.

        Args:
            arbiter: Our own published arbiter.
            on_state: Optional observer, see :func:`wait_for_turn`.
            started: The monotonic timestamp the wait began at.
        """
        self._arbiter = arbiter
        self._on_state = on_state
        self._started = started
        self._next_heartbeat = QUEUE_HEARTBEAT_SECONDS
        self.seen: list[str] = []

    def publish(self, blocked: tuple[str, ...], elapsed: float) -> None:
        """Tell the observer what this wait looks like right now.

        Args:
            blocked: Apps ahead of us; empty means the wait has ended.
            elapsed: Seconds waited so far.
        """
        if self._on_state is not None:
            self._on_state(blocked, elapsed)

    def note(self, blockers: tuple[Claim, ...], elapsed: float) -> None:
        """Record any blocker not seen before, and publish if that changed.

        Args:
            blockers: The live claims currently ahead of us.
            elapsed: Seconds waited so far.
        """
        newly_seen = False
        for claim in blockers:
            if claim.app in self.seen:
                continue
            self.seen.append(claim.app)
            newly_seen = True
            _logger.info(
                "%s is queued behind %s (rank %d) -- waiting with no window",
                self._arbiter.claim.app,
                claim.app,
                claim.rank,
            )
        if newly_seen:
            self.publish(tuple(self.seen), elapsed)

    def heartbeat(self, elapsed: float, deadline: float) -> None:
        """Re-state a still-blocked wait, periodically and at WARNING.

        The wait used to announce itself once, at INFO, and then go silent:
        a 2h58m block on 2026-08-30 was indistinguishable from a healthy idle
        unit in ``systemctl status``.

        Args:
            elapsed: Seconds waited so far.
            deadline: The runaway backstop, for context in the message.
        """
        if elapsed < self._next_heartbeat:
            return
        _logger.warning(
            "%s has been queued behind %s for %.0fs with no window -- "
            "still waiting (deadline %.0fs)",
            self._arbiter.claim.app,
            ", ".join(self.seen),
            elapsed,
            deadline,
        )
        self.publish(tuple(self.seen), elapsed)
        while self._next_heartbeat <= elapsed:
            self._next_heartbeat += QUEUE_HEARTBEAT_SECONDS


def wait_for_turn(
    arbiter: Arbiter,
    *,
    poll: float = QUEUE_POLL_SECONDS,
    deadline: float = QUEUE_DEADLINE_SECONDS,
    on_state: Callable[[tuple[str, ...], float], None] | None = None,
    timebase: Timebase | None = None,
) -> QueueResult:
    """Block, showing nothing, until no stronger locker holds the screen.

    Args:
        arbiter: Our own arbiter, already published so that lower-ranked apps
            queue behind us in turn.
        poll: Seconds between checks. Liveness comes from ``flock``, so a
            SIGKILLed incumbent is noticed on the very next tick.
        deadline: Runaway backstop in seconds.
        on_state: Called with ``(blocked_by, elapsed)`` when the blocked set
            first appears or changes, on every heartbeat, and once with an
            empty tuple when the wait ends. Lets a caller publish the wait
            somewhere observable -- from outside, a blocked process is
            indistinguishable from a hung one.
        timebase: Injected clock and sleep, for tests.

    Returns:
        A record of the wait.
    """
    time_source = timebase if timebase is not None else Timebase()
    clock = time_source.now

    started = clock()
    wait = _Wait(arbiter, on_state, started)

    while True:
        blockers = stronger_claims(arbiter)
        elapsed = clock() - started
        if not blockers:
            if wait.seen:
                _logger.warning(
                    "%s waited %.0fs behind %s; arming now",
                    arbiter.claim.app,
                    elapsed,
                    ", ".join(wait.seen),
                )
            wait.publish((), elapsed)
            return QueueResult(
                waited_seconds=elapsed, blocked_by=tuple(wait.seen), timed_out=False
            )

        wait.note(blockers, elapsed)
        wait.heartbeat(elapsed, deadline)

        if elapsed >= deadline:
            _logger.error(
                "%s waited %.0fs behind %s and gave up waiting -- arming "
                "anyway rather than leaving the machine unlocked",
                arbiter.claim.app,
                elapsed,
                ", ".join(wait.seen),
            )
            wait.publish((), elapsed)
            return QueueResult(
                waited_seconds=elapsed, blocked_by=tuple(wait.seen), timed_out=True
            )

        time_source.sleep(poll)
