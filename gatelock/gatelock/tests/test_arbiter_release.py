"""Tests for identifying the current holder and releasing a claim.

Split from ``test_arbiter.py`` (250-line cap). ``test_arbiter_lifecycle.py``
keeps publishing and rival evaluation; this one covers who holds the claim
now and what happens when it is given up.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from gatelock._arbiter import (
    RANK_DIET_GUARD,
    RANK_SCREEN_LOCKER,
    RANK_WAKE_ALARM,
    Arbiter,
    Claim,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


DEFAULT_STARTED = "2026-07-25T12:00:00+00:00"


def dead_claim(app: str = "ghost", instance_id: str = "dead") -> Claim:
    """A claim belonging to a process that has since died."""
    return Claim(
        app=app,
        rank=RANK_WAKE_ALARM,
        pid=999999,
        started=DEFAULT_STARTED,
        grab="global",
        disable_vt=True,
        instance_id=instance_id,
    )


def make_claim(
    *,
    rank: int = RANK_SCREEN_LOCKER,
    started: str = DEFAULT_STARTED,
    grab: str = "global",
    disable_vt: bool = True,
) -> Claim:
    """A claim with sensible defaults."""
    return Claim(
        app="test_app",
        rank=rank,
        pid=1234,
        started=started,
        grab=grab,
        disable_vt=disable_vt,
        instance_id="tok",
    )


@pytest.fixture
def arb(tmp_path: Path) -> Iterator[Arbiter]:
    """A published hard-locking arbiter in an isolated runtime dir."""
    arbiter = Arbiter(
        "screen_locker",
        RANK_SCREEN_LOCKER,
        grab="global",
        disable_vt=True,
        runtime_dir=tmp_path / "rt",
    )
    arbiter.publish()
    yield arbiter
    arbiter.release()


def hard(name: str, rank: int, root: Path) -> Arbiter:
    """A hard-locking arbiter."""
    return Arbiter(name, rank, grab="global", disable_vt=True, runtime_dir=root)


class TestHolder:
    """Owning and naming the screen."""

    def test_acquire_and_reacquire(self, arb: Arbiter) -> None:
        """Acquiring twice is idempotent."""
        assert arb.acquire_holder() is True
        assert arb.holds_screen is True
        assert arb.acquire_holder() is True

    def test_second_app_is_blocked(self, arb: Arbiter, tmp_path: Path) -> None:
        """Only one app holds the screen."""
        arb.acquire_holder()
        other = hard("diet_guard", RANK_DIET_GUARD, tmp_path / "rt")
        other.publish()
        assert other.acquire_holder() is False
        other.release()

    def test_blocked_app_learns_the_holder(self, arb: Arbiter, tmp_path: Path) -> None:
        """A failed acquire must not erase the incumbent's claim."""
        arb.acquire_holder()
        other = hard("diet_guard", RANK_DIET_GUARD, tmp_path / "rt")
        other.publish()
        other.acquire_holder()
        holder = other.describe_holder()
        assert holder is not None
        assert holder.app == "screen_locker"
        other.release()

    def test_describe_holder_when_we_hold_it(self, arb: Arbiter) -> None:
        """The holder describes itself without touching the file."""
        arb.acquire_holder()
        holder = arb.describe_holder()
        assert holder is not None
        assert holder.app == "screen_locker"

    def test_describe_holder_no_file(self, arb: Arbiter) -> None:
        """No holder file means nobody holds the screen."""
        assert arb.describe_holder() is None

    def test_describe_holder_stale_lock(self, arb: Arbiter, tmp_path: Path) -> None:
        """A holder file nobody locks means the owner died."""
        (tmp_path / "rt").mkdir(parents=True, exist_ok=True)
        (tmp_path / "rt" / "holder.lock").write_text(
            dead_claim().to_json(), encoding="utf-8"
        )
        assert arb.describe_holder() is None

    def test_describe_holder_oserror(self, arb: Arbiter, tmp_path: Path) -> None:
        """An unreadable holder file is reported as no holder."""
        (tmp_path / "rt").mkdir(parents=True, exist_ok=True)
        (tmp_path / "rt" / "holder.lock").write_text("{}", encoding="utf-8")
        with patch("gatelock._claims.Path.open", side_effect=OSError("denied")):
            assert arb.describe_holder() is None


class TestRelease:
    """Clean exit hands the screen over."""

    def test_release_lets_the_next_app_in(self, tmp_path: Path) -> None:
        """The alarm -> workout handoff: a clean exit must free the screen."""
        alarm = hard("wake_alarm", RANK_WAKE_ALARM, tmp_path / "rt")
        alarm.publish()
        assert alarm.acquire_holder() is True

        workout = hard("screen_locker", RANK_SCREEN_LOCKER, tmp_path / "rt")
        workout.publish()
        assert workout.acquire_holder() is False
        assert workout.evaluate().may_arm is False

        alarm.release()

        assert workout.acquire_holder() is True
        assert workout.evaluate().may_arm is True
        workout.release()

    def test_release_is_idempotent(self, tmp_path: Path) -> None:
        """Releasing twice is safe."""
        arbiter = hard("a", RANK_DIET_GUARD, tmp_path / "rt")
        arbiter.publish()
        arbiter.release()
        arbiter.release()
        assert arbiter.holds_screen is False

    def test_release_tolerates_unlink_failure(self, tmp_path: Path) -> None:
        """A claim that cannot be removed does not break teardown."""
        arbiter = hard("a", RANK_DIET_GUARD, tmp_path / "rt")
        arbiter.publish()
        with patch("gatelock._claims.Path.unlink", side_effect=OSError("busy")):
            arbiter.release()

    def test_claim_property(self, arb: Arbiter) -> None:
        """The arbiter exposes its own claim."""
        assert arb.claim.app == "screen_locker"
        assert arb.claim.rank == RANK_SCREEN_LOCKER


class TestReleaseHandleClose:
    """Handle-close failures are non-fatal."""

    def test_close_oserror_is_swallowed(self, tmp_path: Path) -> None:
        """A failing close does not stop the release."""
        arbiter = hard("a", RANK_DIET_GUARD, tmp_path / "rt")
        arbiter.publish()
        arbiter.acquire_holder()
        bad = MagicMock()
        bad.close.side_effect = OSError("nope")
        real_handle = arbiter._holder_handle
        assert real_handle is not None
        real_handle.close()
        arbiter._holder_handle = bad
        arbiter.release()
        assert arbiter.holds_screen is False
