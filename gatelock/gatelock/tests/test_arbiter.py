"""Tests for cross-app arbitration.

The strength-check table is the most important thing here: it is the invariant
that stops priority rank from becoming a way to disarm a stronger lock.
"""

from __future__ import annotations

import errno
import os
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from gatelock._arbiter import (
    RANK_DIET_GUARD,
    RANK_SCREEN_LOCKER,
    RANK_WAKE_ALARM,
    Arbiter,
    Claim,
    _same_file,
    _try_lock,
    default_runtime_dir,
    grab_strength,
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


class TestGrabStrength:
    """Unknown grab kinds must never rank as strong."""

    @pytest.mark.parametrize(
        ("kind", "expected"),
        [("none", 0), ("local", 1), ("global", 2), ("something-new", 0)],
    )
    def test_ordering(self, kind: str, expected: int) -> None:
        """Known kinds order none < local < global; unknown sorts weakest."""
        assert grab_strength(kind) == expected


class TestStrengthCheck:
    """THE anti-bypass invariant, as a table."""

    @pytest.mark.parametrize(
        ("their_grab", "their_vt", "our_grab", "our_vt", "strong_enough"),
        [
            ("global", True, "global", True, True),
            ("global", True, "local", False, True),
            ("global", True, "none", False, True),
            ("none", False, "global", True, False),
            ("local", True, "global", True, False),
            ("global", False, "global", True, False),
            ("local", False, "local", False, True),
            ("none", True, "none", True, True),
        ],
    )
    def test_table(
        self,
        their_grab: str,
        our_grab: str,
        *,
        their_vt: bool,
        our_vt: bool,
        strong_enough: bool,
    ) -> None:
        """Standing down requires being no weaker on BOTH axes."""
        theirs = make_claim(grab=their_grab, disable_vt=their_vt)
        ours = make_claim(grab=our_grab, disable_vt=our_vt)
        assert theirs.at_least_as_strong_as(ours) is strong_enough


class TestClaimSerialisation:
    """A malformed claim must never stop a locker arming."""

    def test_round_trip(self) -> None:
        """A claim survives serialisation."""
        claim = make_claim()
        assert Claim.from_json(claim.to_json()) == claim

    @pytest.mark.parametrize(
        "text", ["not json", "[]", '"a string"', "123", '{"app": "x"}']
    )
    def test_unusable_input_returns_none(self, text: str) -> None:
        """Bad JSON, wrong type, or missing fields all yield None."""
        assert Claim.from_json(text) is None

    def test_wrong_field_type_returns_none(self) -> None:
        """A non-numeric rank is rejected rather than raising."""
        assert (
            Claim.from_json(
                '{"app":"a","rank":"x","pid":1,"started":"s",'
                '"grab":"none","disable_vt":false,"instance_id":"t"}'
            )
            is None
        )

    def test_sort_key_orders_by_rank_then_start_then_pid(self) -> None:
        """Highest rank first, then earliest, then lowest pid."""
        high = make_claim(rank=300)
        low_early = make_claim(rank=100, started="2026-01-01T00:00:00+00:00")
        low_late = make_claim(rank=100, started="2026-12-01T00:00:00+00:00")
        ordered = sorted([low_late, high, low_early], key=Claim.sort_key)
        assert [c.rank for c in ordered] == [300, 100, 100]
        assert ordered[1] is low_early


class TestRuntimeDir:
    """Where claims live."""

    def test_env_override_wins(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """GATELOCK_RUNTIME_DIR takes precedence."""
        monkeypatch.setenv("GATELOCK_RUNTIME_DIR", str(tmp_path / "override"))
        assert default_runtime_dir() == tmp_path / "override"

    def test_xdg_runtime_dir(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Falls back to XDG_RUNTIME_DIR/gatelock."""
        monkeypatch.delenv("GATELOCK_RUNTIME_DIR", raising=False)
        monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "xdg"))
        assert default_runtime_dir() == tmp_path / "xdg" / "gatelock"

    def test_tempdir_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """With neither env var, a per-uid temp directory is used."""
        monkeypatch.delenv("GATELOCK_RUNTIME_DIR", raising=False)
        monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
        assert str(os.getuid()) in str(default_runtime_dir())


class TestTryLock:
    """flock wrapper behaviour."""

    def test_contended_returns_false(self, tmp_path: Path) -> None:
        """EAGAIN/EACCES mean somebody else holds it."""
        path = tmp_path / "f"
        path.write_text("x", encoding="utf-8")
        with path.open("r+", encoding="utf-8") as first:
            assert _try_lock(first) is True
            with path.open("r+", encoding="utf-8") as second:
                assert _try_lock(second) is False

    def test_other_oserror_propagates(self, tmp_path: Path) -> None:
        """An unexpected errno is a real problem and must not be swallowed."""
        path = tmp_path / "f"
        path.write_text("x", encoding="utf-8")
        with path.open("r+", encoding="utf-8") as handle:
            exc = OSError()
            exc.errno = errno.ENOSPC
            with (
                patch("gatelock._arbiter.fcntl.flock", side_effect=exc),
                pytest.raises(OSError, match=r"^$"),
            ):
                _try_lock(handle)

    def test_same_file_false_on_missing_path(self, tmp_path: Path) -> None:
        """A vanished path is not the same file."""
        path = tmp_path / "gone"
        path.write_text("x", encoding="utf-8")
        with path.open("r+", encoding="utf-8") as handle:
            path.unlink()
            assert _same_file(handle, path) is False


class TestPublishAndLiveClaims:
    """Publishing, liveness and reaping."""

    def test_own_claim_is_live(self, arb: Arbiter) -> None:
        """A published claim shows up as live."""
        assert [c.app for c in arb.live_claims()] == ["screen_locker"]

    def test_no_claims_dir(self, tmp_path: Path) -> None:
        """Before anyone publishes, there are no claims."""
        assert hard("a", 1, tmp_path / "empty").live_claims() == ()

    def test_dead_claim_is_reaped(self, arb: Arbiter, tmp_path: Path) -> None:
        """An unlocked claim file proves its owner died; it is deleted."""
        dead = tmp_path / "rt" / "claims" / "0300-999-dead.json"
        dead.write_text(dead_claim().to_json(), "utf-8")
        assert "ghost" not in [c.app for c in arb.live_claims()]
        assert not dead.exists()

    def test_unreadable_claim_ignored(self, arb: Arbiter, tmp_path: Path) -> None:
        """A claim that cannot be opened is skipped, not fatal."""
        bad = tmp_path / "rt" / "claims" / "0100-1-bad.json"
        bad.write_text("{}", encoding="utf-8")
        with patch("gatelock._arbiter.Path.open", side_effect=OSError("denied")):
            assert arb.live_claims() == ()

    def test_reap_skips_recreated_file(self, arb: Arbiter, tmp_path: Path) -> None:
        """A claim recreated between lock and unlink is not deleted."""
        dead = tmp_path / "rt" / "claims" / "0300-999-dead.json"
        dead.write_text(dead_claim().to_json(), "utf-8")
        with patch("gatelock._arbiter._same_file", return_value=False):
            arb.live_claims()
        assert dead.exists()

    def test_reap_tolerates_unlink_failure(self, arb: Arbiter, tmp_path: Path) -> None:
        """A failed unlink is logged, not raised."""
        dead = tmp_path / "rt" / "claims" / "0300-999-dead.json"
        dead.write_text(dead_claim().to_json(), "utf-8")
        with patch("gatelock._arbiter.Path.unlink", side_effect=OSError("busy")):
            live = arb.live_claims()
        # The reap is best-effort: the claim is excluded from the live set even
        # when the file itself cannot be removed.
        assert "ghost" not in [c.app for c in live]

    def test_publish_twice_warns_and_continues(self, tmp_path: Path) -> None:
        """A second publish on a locked path continues unpublished."""
        arbiter = hard("a", RANK_DIET_GUARD, tmp_path / "rt")
        arbiter.publish()
        with patch("gatelock._arbiter._try_lock", return_value=False):
            arbiter.publish()  # must not raise
        arbiter.release()


class TestEvaluate:
    """Who may arm."""

    def test_clear_when_alone(self, arb: Arbiter) -> None:
        """Nothing pending means arm."""
        verdict = arb.evaluate()
        assert verdict.may_arm is True
        assert verdict.reason == "clear"
        assert verdict.blocked_by is None

    def test_lower_rank_does_not_block(self, arb: Arbiter, tmp_path: Path) -> None:
        """A weaker-ranked peer never blocks."""
        diet = hard("diet_guard", RANK_DIET_GUARD, tmp_path / "rt")
        diet.publish()
        assert arb.evaluate().may_arm is True
        diet.release()

    def test_stronger_higher_rank_blocks(self, arb: Arbiter, tmp_path: Path) -> None:
        """A higher-ranked, equally strong app wins."""
        alarm = hard("wake_alarm", RANK_WAKE_ALARM, tmp_path / "rt")
        alarm.publish()
        verdict = arb.evaluate()
        assert verdict.may_arm is False
        assert verdict.reason == "outranked"
        assert verdict.blocked_by is not None
        assert verdict.blocked_by.app == "wake_alarm"
        alarm.release()

    def test_weaker_higher_rank_arms_anyway(self, arb: Arbiter, tmp_path: Path) -> None:
        """Rank must never be able to reduce total lock strength."""
        soft_alarm = Arbiter(
            "wake_alarm",
            RANK_WAKE_ALARM,
            grab="none",
            disable_vt=False,
            runtime_dir=tmp_path / "rt",
        )
        soft_alarm.publish()
        verdict = arb.evaluate()
        assert verdict.may_arm is True
        assert verdict.reason == "weaker-incumbent-armed-anyway"
        soft_alarm.release()


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
        with patch("gatelock._arbiter.Path.open", side_effect=OSError("denied")):
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
        with patch("gatelock._arbiter.Path.unlink", side_effect=OSError("busy")):
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
