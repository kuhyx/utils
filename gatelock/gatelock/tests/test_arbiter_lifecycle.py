"""Tests for an arbiter claim's life after it is taken.

Split from ``test_arbiter.py`` (250-line cap): that file covers grab
strength, claim serialisation, the runtime dir and taking the lock; this one
covers publishing, evaluating rivals, describing the holder, and release.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

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
