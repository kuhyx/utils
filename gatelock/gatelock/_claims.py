"""The claim an app publishes while it holds the screen, and how to read one.

Split from :mod:`gatelock._arbiter`, which keeps the arbiter itself. A claim
is a small JSON document under the runtime dir, held open with an advisory
lock for as long as its process lives -- so "is this claim live?" is answered
by trying to take that lock, not by trusting the file's contents.

Re-exported from :mod:`gatelock._arbiter`, so existing imports keep working.
"""

from __future__ import annotations

from dataclasses import dataclass
import errno
import fcntl
import json
import logging
import os
from pathlib import Path
import tempfile
from typing import IO, Final, Literal

_logger = logging.getLogger(__name__)

_RUNTIME_DIR_ENV: Final = "GATELOCK_RUNTIME_DIR"

VerdictReason = Literal["clear", "outranked", "weaker-incumbent-armed-anyway"]


_GRAB_STRENGTH: Final[dict[str, int]] = {"none": 0, "local": 1, "global": 2}


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


def _reap(handle: IO[str], path: Path) -> None:
    """Delete a claim whose owner has died, unless it was recreated.

    Args:
        handle: The open handle whose lock proved the owner is gone.
        path: The claim file to remove.
    """
    if not _same_file(handle, path):
        _logger.debug("claim %s was recreated while reaping; leaving it", path)
        return
    try:
        path.unlink()
    except OSError as exc:
        _logger.debug("could not reap stale claim %s: %s", path, exc)


def _read_if_live(path: Path) -> Claim | None:
    """Return the claim at `path` if its owner is alive; else reap it.

    Taking the advisory lock succeeds only when nobody holds it, which means
    the owning process is gone -- so a successful lock is the proof of death,
    and the file is removed rather than returned.
    """
    try:
        handle = path.open("r+", encoding="utf-8")
    except OSError:
        return None
    with handle:
        if _try_lock(handle):
            _reap(handle, path)
            return None
        try:
            return Claim.from_json(handle.read())
        except OSError:
            return None


def live_claims(claims_dir: Path) -> tuple[Claim, ...]:
    """Every claim under `claims_dir` whose owning process is still alive.

    Dead owners' claims are reaped as a side effect -- proving a claim is
    stale and deleting it are the same operation.

    Args:
        claims_dir: Directory holding the `*.json` claim files.

    Returns:
        The live claims, in arbitration order.
    """
    if not claims_dir.is_dir():
        return ()
    claims = [
        claim
        for path in sorted(claims_dir.glob("*.json"))
        if (claim := _read_if_live(path)) is not None
    ]
    return tuple(sorted(claims, key=Claim.sort_key))


def read_claim_if_held(path: Path) -> Claim | None:
    """The claim at `path`, but only while a live process still holds it.

    Taking the advisory lock succeeds only when nobody holds it, so a
    successful lock means the screen is free and there is no holder to name.

    Args:
        path: The holder claim file.

    Returns:
        The holder's claim, or None if the lock was free or unreadable.
    """
    try:
        with path.open("r+", encoding="utf-8") as handle:
            if _try_lock(handle):
                return None
            return Claim.from_json(handle.read())
    except OSError:
        return None
