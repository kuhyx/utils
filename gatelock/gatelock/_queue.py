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


def wait_for_turn(
    arbiter: Arbiter,
    *,
    poll: float = QUEUE_POLL_SECONDS,
    deadline: float = QUEUE_DEADLINE_SECONDS,
    sleep: Callable[[float], None] | None = None,
    now: Callable[[], float] | None = None,
) -> QueueResult:
    """Block, showing nothing, until no stronger locker holds the screen.

    Args:
        arbiter: Our own arbiter, already published so that lower-ranked apps
            queue behind us in turn.
        poll: Seconds between checks. Liveness comes from ``flock``, so a
            SIGKILLed incumbent is noticed on the very next tick.
        deadline: Runaway backstop in seconds.
        sleep: Injected for tests.
        now: Injected monotonic clock, for tests.

    Returns:
        A record of the wait.
    """
    rest = sleep if sleep is not None else time.sleep
    clock = now if now is not None else time.monotonic

    started = clock()
    seen: list[str] = []
    while True:
        blockers = stronger_claims(arbiter)
        if not blockers:
            waited = clock() - started
            if seen:
                _logger.warning(
                    "%s waited %.0fs behind %s; arming now",
                    arbiter.claim.app,
                    waited,
                    ", ".join(seen),
                )
            return QueueResult(
                waited_seconds=waited, blocked_by=tuple(seen), timed_out=False
            )

        for claim in blockers:
            if claim.app not in seen:
                seen.append(claim.app)
                _logger.info(
                    "%s is queued behind %s (rank %d) -- waiting with no window",
                    arbiter.claim.app,
                    claim.app,
                    claim.rank,
                )

        elapsed = clock() - started
        if elapsed >= deadline:
            _logger.error(
                "%s waited %.0fs behind %s and gave up waiting -- arming "
                "anyway rather than leaving the machine unlocked",
                arbiter.claim.app,
                elapsed,
                ", ".join(seen),
            )
            return QueueResult(
                waited_seconds=elapsed, blocked_by=tuple(seen), timed_out=True
            )

        rest(poll)
