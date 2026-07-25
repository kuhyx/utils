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

from dataclasses import dataclass
from datetime import datetime, timezone
import errno
import fcntl
import json
import logging
import os
from pathlib import Path
import tempfile
from typing import IO, Final, Literal
import uuid

_logger = logging.getLogger(__name__)

RANK_WAKE_ALARM: Final = 300
RANK_SCREEN_LOCKER: Final = 200
RANK_DIET_GUARD: Final = 100

_RUNTIME_DIR_ENV: Final = "GATELOCK_RUNTIME_DIR"
_CLAIMS_DIRNAME: Final = "claims"
_HOLDER_FILENAME: Final = "holder.lock"

# Ordering for the strength check. A stand-down is only safe towards an
# incumbent whose grab is at least this strong.
_GRAB_STRENGTH: Final[dict[str, int]] = {"none": 0, "local": 1, "global": 2}

VerdictReason = Literal["clear", "outranked", "weaker-incumbent-armed-anyway"]


def _utc_now_iso() -> str:
    """Return an ISO-8601 UTC timestamp, sortable as a plain string."""
    return datetime.now(tz=timezone.utc).isoformat()


def grab_strength(grab: str) -> int:
    """Return the comparable strength of a grab kind.

    Unknown values sort as the weakest possible, so a future grab kind can
    never be silently treated as strong enough to stand down for.
    """
    return _GRAB_STRENGTH.get(grab, 0)


@dataclass(frozen=True)
class Claim:
    """One app's declared intent to hold the screen."""

    app: str
    rank: int
    pid: int
    started: str
    grab: str
    disable_vt: bool
    instance_id: str
    """Identifies the *arbiter*, not the process.

    A pid is not unique enough: one process may legitimately host two
    arbiters, and the whole test suite does exactly that to exercise real
    ``flock`` contention without spawning subprocesses.
    """

    def to_json(self) -> str:
        """Serialise this claim for its on-disk file."""
        return json.dumps(
            {
                "app": self.app,
                "rank": self.rank,
                "pid": self.pid,
                "started": self.started,
                "grab": self.grab,
                "disable_vt": self.disable_vt,
                "instance_id": self.instance_id,
            }
        )

    @classmethod
    def from_json(cls, text: str) -> Claim | None:
        """Parse a claim file's contents, or None if it is unusable.

        A malformed claim is treated as absent rather than fatal: a half-written
        file must never be able to stop a locker from arming.
        """
        try:
            raw = json.loads(text)
        except json.JSONDecodeError:
            return None
        if not isinstance(raw, dict):
            return None
        try:
            return cls(
                app=str(raw["app"]),
                rank=int(raw["rank"]),
                pid=int(raw["pid"]),
                started=str(raw["started"]),
                grab=str(raw["grab"]),
                disable_vt=bool(raw["disable_vt"]),
                instance_id=str(raw["instance_id"]),
            )
        except (KeyError, TypeError, ValueError):
            return None

    def at_least_as_strong_as(self, other: Claim) -> bool:
        """Whether this claim locks at least as firmly as ``other``."""
        return (
            grab_strength(self.grab) >= grab_strength(other.grab)
            and self.disable_vt >= other.disable_vt
        )

    def sort_key(self) -> tuple[int, str, int]:
        """Rank descending, then earliest start, then lowest pid."""
        return (-self.rank, self.started, self.pid)


@dataclass(frozen=True)
class ArbiterVerdict:
    """Whether this app may arm, and why."""

    may_arm: bool
    blocked_by: Claim | None
    reason: VerdictReason


def default_runtime_dir() -> Path:
    """Return the directory holding claims and the holder lock.

    Prefers ``$XDG_RUNTIME_DIR`` (tmpfs, so it self-clears on reboot) and falls
    back to a per-uid temp directory when that is unset or unwritable.
    """
    override = os.environ.get(_RUNTIME_DIR_ENV)
    if override:
        return Path(override)
    xdg = os.environ.get("XDG_RUNTIME_DIR")
    if xdg:
        return Path(xdg) / "gatelock"
    return Path(tempfile.gettempdir()) / f"gatelock-{os.getuid()}"


def _try_lock(handle: IO[str]) -> bool:
    """Try to take an exclusive non-blocking flock. True if acquired."""
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        if exc.errno in {errno.EACCES, errno.EAGAIN}:
            return False
        raise
    return True


def _same_file(handle: IO[str], path: Path) -> bool:
    """Whether ``path`` still names the file behind ``handle``.

    Guards the reap below: between locking a dead app's claim and unlinking it,
    a fresh process may have recreated the same path. Comparing inodes stops us
    deleting the newcomer's claim.
    """
    try:
        return os.fstat(handle.fileno()).st_ino == path.stat().st_ino
    except OSError:
        return False


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
        stale and deleting it are the same operation.
        """
        if not self._claims_dir.is_dir():
            return ()
        claims: list[Claim] = []
        for path in sorted(self._claims_dir.glob("*.json")):
            claim = self._read_if_live(path)
            if claim is not None:
                claims.append(claim)
        return tuple(sorted(claims, key=Claim.sort_key))

    def _read_if_live(self, path: Path) -> Claim | None:
        """Return the claim at ``path`` if its owner is alive; else reap it."""
        try:
            handle = path.open("r+", encoding="utf-8")
        except OSError:
            return None
        with handle:
            if _try_lock(handle):
                # We got the lock, so nobody holds it, so the owner is gone.
                self._reap(handle, path)
                return None
            try:
                return Claim.from_json(handle.read())
            except OSError:
                return None

    def _reap(self, handle: IO[str], path: Path) -> None:
        """Delete a claim whose owner has died, unless it was recreated."""
        if not _same_file(handle, path):
            _logger.debug("claim %s was recreated while reaping; leaving it", path)
            return
        try:
            path.unlink()
        except OSError as exc:
            _logger.debug("could not reap stale claim %s: %s", path, exc)

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
        try:
            with path.open("r+", encoding="utf-8") as handle:
                if _try_lock(handle):
                    # Lock was free, so no live app holds the screen.
                    return None
                return Claim.from_json(handle.read())
        except OSError:
            return None

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
