"""Decide which of N locker apps may hold the screen.

On 2026-07-25 two lockers armed at the same boot. One won the X grab; the
other spun forever in a retry loop, logging that "a fullscreen game" held the
grab. No game was running -- the holder was the other locker. Nothing
coordinated them because nothing could: each app only knew about itself.

This module is that coordination. Every app publishes a *claim* before it
builds any window, and the highest-ranked live claim wins. Ranks, highest
first:

* ``RANK_WAKE_ALARM``    -- you have to wake up before you can do anything else
* ``RANK_SCREEN_LOCKER`` -- then you work out
* ``RANK_DIET_GUARD``    -- then you eat

Two properties do the real work.

**Liveness is proved by the kernel, not by a heartbeat.** Each app holds an
``flock`` on its own claim file for its entire life. The kernel drops that lock
on *any* death, including ``SIGKILL``, OOM and a crashed X server. So a reader
that successfully locks somebody else's claim has thereby proved the owner is
dead. No PID scanning, no timeouts, no clock skew.

**Rank can never weaken the lock.** Deferring to a higher-ranked app would be a
bypass if that app locked less firmly -- "start the alarm to disarm the workout
lock". So an app stands down only for an incumbent that is at least as strong
on *both* axes (grab kind and VT disabling). Otherwise it says so, loudly, and
arms anyway. See :meth:`Arbiter.evaluate`.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
from typing import IO, TYPE_CHECKING, Final
import uuid

from gatelock._claims import (
    ArbiterVerdict,
    Claim,
    _try_lock,
    default_runtime_dir,
    grab_strength,
    live_claims,
    read_claim_if_held,
)

if TYPE_CHECKING:
    from pathlib import Path

_logger = logging.getLogger(__name__)

# Re-exported after the 250-line split: `from gatelock._arbiter import
# Claim` is used by _window, the tests and gatelock's own __init__.
__all__ = [
    "RANK_DIET_GUARD",
    "RANK_SCREEN_LOCKER",
    "RANK_WAKE_ALARM",
    "Arbiter",
    "ArbiterVerdict",
    "Claim",
    "default_runtime_dir",
    "grab_strength",
]


RANK_WAKE_ALARM: Final = 300
RANK_SCREEN_LOCKER: Final = 200
RANK_DIET_GUARD: Final = 100

_CLAIMS_DIRNAME: Final = "claims"
_HOLDER_FILENAME: Final = "holder.lock"

# Ordering for the strength check. A stand-down is only safe towards an
# incumbent whose grab is at least this strong.


def _utc_now_iso() -> str:
    """Return an ISO-8601 UTC timestamp, sortable as a plain string."""
    return datetime.now(tz=timezone.utc).isoformat()


class Arbiter:
    """Publishes this app's claim and reports whether it may arm."""

    def __init__(
        self,
        app: str,
        rank: int,
        *,
        grab: str,
        disable_vt: bool,
        runtime_dir: Path | None = None,
    ) -> None:
        """Prepare an arbiter for one app.

        Args:
            app: Human-readable app name, used in logs.
            rank: Priority; higher wins. Use the ``RANK_*`` constants.
            grab: The grab kind this app will take (``none``/``local``/``global``).
            disable_vt: Whether this app will disable VT switching.
            runtime_dir: Override for the state directory. Tests pass a tmp_path.
        """
        self._root = runtime_dir if runtime_dir is not None else default_runtime_dir()
        self._claims_dir = self._root / _CLAIMS_DIRNAME
        self._claim = Claim(
            app=app,
            rank=rank,
            pid=os.getpid(),
            started=_utc_now_iso(),
            grab=grab,
            disable_vt=disable_vt,
            instance_id=uuid.uuid4().hex,
        )
        name = f"{rank:04d}-{self._claim.pid}-{self._claim.instance_id}.json"
        self._claim_path = self._claims_dir / name
        self._claim_handle: IO[str] | None = None
        self._holder_handle: IO[str] | None = None

    @property
    def claim(self) -> Claim:
        """This app's own claim."""
        return self._claim

    @property
    def holds_screen(self) -> bool:
        """Whether this arbiter currently owns the holder lock."""
        return self._holder_handle is not None

    def publish(self) -> None:
        """Write and lock this app's claim, so others can see it is alive."""
        self._claims_dir.mkdir(parents=True, exist_ok=True)
        handle = self._claim_path.open("a+", encoding="utf-8")
        if not _try_lock(handle):
            # Only reachable if this pid's claim file is already locked, which
            # would mean two Arbiters in one process. Close and carry on
            # unpublished rather than dying.
            handle.close()
            _logger.warning(
                "could not lock own claim %s; continuing unpublished",
                self._claim_path,
            )
            return
        handle.seek(0)
        handle.truncate()
        handle.write(self._claim.to_json())
        handle.flush()
        self._claim_handle = handle

    def live_claims(self) -> tuple[Claim, ...]:
        """Return every claim whose owning process is still alive.

        Dead owners' claims are reaped as a side effect -- proving a claim is
        stale and deleting it are the same operation. See
        :func:`gatelock._claims.live_claims`.
        """
        return live_claims(self._claims_dir)

    def evaluate(self) -> ArbiterVerdict:
        """Decide whether this app may arm.

        Standing down is only permitted for a *stronger or equal* incumbent.
        Deferring to a weaker one would turn rank into a bypass, so that case
        arms anyway and says so at ERROR.
        """
        mine = self._claim.instance_id
        others = [c for c in self.live_claims() if c.instance_id != mine]
        stronger_rank = [c for c in others if c.rank > self._claim.rank]
        if not stronger_rank:
            return ArbiterVerdict(may_arm=True, blocked_by=None, reason="clear")

        winner = min(stronger_rank, key=Claim.sort_key)
        if winner.at_least_as_strong_as(self._claim):
            return ArbiterVerdict(may_arm=False, blocked_by=winner, reason="outranked")
        _logger.error(
            "%s (rank %d) outranks %s (rank %d) but locks more weakly "
            "(grab=%s vt=%s vs grab=%s vt=%s); arming anyway rather than "
            "letting rank weaken the lock",
            winner.app,
            winner.rank,
            self._claim.app,
            self._claim.rank,
            winner.grab,
            winner.disable_vt,
            self._claim.grab,
            self._claim.disable_vt,
        )
        return ArbiterVerdict(
            may_arm=True,
            blocked_by=winner,
            reason="weaker-incumbent-armed-anyway",
        )

    def acquire_holder(self) -> bool:
        """Take the holder lock, marking this app as owning the screen."""
        if self._holder_handle is not None:
            return True
        self._root.mkdir(parents=True, exist_ok=True)
        # Opened "a+", never "w": "w" truncates at open() time, which happens
        # BEFORE the lock attempt. A losing contender would therefore erase the
        # incumbent's claim on its way out, and the app that most needs to know
        # who holds the screen would find an empty file.
        handle = (self._root / _HOLDER_FILENAME).open("a+", encoding="utf-8")
        if not _try_lock(handle):
            handle.close()
            return False
        handle.seek(0)
        handle.truncate()
        handle.write(self._claim.to_json())
        handle.flush()
        self._holder_handle = handle
        return True

    def describe_holder(self) -> Claim | None:
        """Return the claim of whichever app holds the screen, if any.

        Used to replace the old "a fullscreen game holds it" guess with the
        truth, which on 2026-07-25 would have named diet_guard immediately.
        """
        path = self._root / _HOLDER_FILENAME
        if not path.is_file():
            return None
        if self._holder_handle is not None:
            return self._claim
        return read_claim_if_held(path)

    def release(self) -> None:
        """Drop the holder lock and this app's claim.

        Must run on every exit path. ``flock`` covers a killed process for
        free, but a *cleanly* exiting app has to release explicitly -- the
        morning routine runs the alarm and then the workout locker as
        sequential subprocesses, and a lingering claim would make the workout
        locker stand down against an app that had already finished.
        """
        for handle in (self._holder_handle, self._claim_handle):
            if handle is not None:
                try:
                    handle.close()
                except OSError as exc:  # pragma: no cover - close rarely fails
                    _logger.debug("ignoring error closing arbiter handle: %s", exc)
        self._holder_handle = None
        self._claim_handle = None
        try:
            self._claim_path.unlink(missing_ok=True)
        except OSError as exc:
            _logger.debug("could not remove own claim: %s", exc)
