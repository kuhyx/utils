"""Tests for the layered wait."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from gatelock import RANK_DIET_GUARD, RANK_SCREEN_LOCKER, RANK_WAKE_ALARM, Arbiter
from gatelock._queue import (
    QUEUE_HEARTBEAT_SECONDS,
    Timebase,
    stronger_claims,
    wait_for_turn,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

_RANK_LEETCODE_GUARD = 150


def make_arbiter(app: str, rank: int, runtime: Path) -> Arbiter:
    arbiter = Arbiter(app, rank, grab="global", disable_vt=True, runtime_dir=runtime)
    arbiter.publish()
    return arbiter


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0
        self.slept: list[float] = []

    def now(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.value += seconds


def test_an_empty_ladder_arms_immediately(tmp_path: Path) -> None:
    arbiter = make_arbiter("leetcode_guard", _RANK_LEETCODE_GUARD, tmp_path)
    clock = FakeClock()

    result = wait_for_turn(arbiter, timebase=Timebase(sleep=clock.sleep, now=clock.now))

    assert not result.queued
    assert not result.timed_out
    assert clock.slept == []
    arbiter.release()


def test_we_queue_behind_the_workout_lock_and_arm_when_it_finishes(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Your rule, exactly: the workout lock shows first, then this one -- and
    this one never exits just because that one is running."""
    workout = make_arbiter("screen_locker", RANK_SCREEN_LOCKER, tmp_path)
    ours = make_arbiter("leetcode_guard", _RANK_LEETCODE_GUARD, tmp_path)
    clock = FakeClock()

    released = {"done": False}

    def sleep(seconds: float) -> None:
        clock.sleep(seconds)
        if not released["done"]:
            workout.release()
            released["done"] = True

    with caplog.at_level(logging.INFO):
        result = wait_for_turn(ours, timebase=Timebase(sleep=sleep, now=clock.now))

    assert result.queued
    assert result.blocked_by == ("screen_locker",)
    assert not result.timed_out
    assert result.waited_seconds > 0
    ours.release()


def test_a_lower_ranked_locker_is_not_waited_for(tmp_path: Path) -> None:
    """diet_guard sits below us, so it queues behind us -- not the reverse."""
    diet = make_arbiter("diet_guard", RANK_DIET_GUARD, tmp_path)
    ours = make_arbiter("leetcode_guard", _RANK_LEETCODE_GUARD, tmp_path)
    clock = FakeClock()

    result = wait_for_turn(ours, timebase=Timebase(sleep=clock.sleep, now=clock.now))

    assert not result.queued
    diet.release()
    ours.release()


def test_every_higher_ranked_app_is_named_once(tmp_path: Path) -> None:
    alarm = make_arbiter("wake_alarm", RANK_WAKE_ALARM, tmp_path)
    workout = make_arbiter("screen_locker", RANK_SCREEN_LOCKER, tmp_path)
    ours = make_arbiter("leetcode_guard", _RANK_LEETCODE_GUARD, tmp_path)
    clock = FakeClock()

    def sleep(seconds: float) -> None:
        clock.sleep(seconds)
        alarm.release()
        workout.release()

    result = wait_for_turn(ours, timebase=Timebase(sleep=sleep, now=clock.now))

    assert set(result.blocked_by) == {"wake_alarm", "screen_locker"}
    ours.release()


def test_the_deadline_arms_anyway_rather_than_leaving_the_pc_unlocked(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The backstop must never mean "give up and let them through"."""
    workout = make_arbiter("screen_locker", RANK_SCREEN_LOCKER, tmp_path)
    ours = make_arbiter("leetcode_guard", _RANK_LEETCODE_GUARD, tmp_path)
    clock = FakeClock()

    with caplog.at_level(logging.ERROR):
        result = wait_for_turn(
            ours,
            poll=10.0,
            deadline=30.0,
            timebase=Timebase(sleep=clock.sleep, now=clock.now),
        )

    assert result.timed_out
    assert result.blocked_by == ("screen_locker",)
    assert any(record.levelno == logging.ERROR for record in caplog.records)
    workout.release()
    ours.release()


def test_stronger_claims_ignores_our_own(tmp_path: Path) -> None:
    ours = make_arbiter("leetcode_guard", _RANK_LEETCODE_GUARD, tmp_path)

    assert stronger_claims(ours) == ()
    ours.release()


def test_a_dead_holder_stops_blocking_us(tmp_path: Path) -> None:
    """Liveness is the kernel's flock, so a SIGKILLed locker is noticed on the
    next tick -- no heartbeats, no staleness heuristics."""
    workout = make_arbiter("screen_locker", RANK_SCREEN_LOCKER, tmp_path)
    ours = make_arbiter("leetcode_guard", _RANK_LEETCODE_GUARD, tmp_path)

    assert len(stronger_claims(ours)) == 1
    workout.release()
    assert stronger_claims(ours) == ()
    ours.release()


def test_a_long_wait_is_restated_periodically(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A block used to announce itself once, at INFO, then go silent.

    On 2026-08-30 screen_locker sat behind wake_alarm for 10716s and
    ``systemctl status`` showed an active, quiet, apparently healthy unit.
    """
    theirs = make_arbiter("wake_alarm", RANK_WAKE_ALARM, tmp_path)
    ours = make_arbiter("screen_locker", RANK_SCREEN_LOCKER, tmp_path)
    clock = FakeClock()
    released = 3 * QUEUE_HEARTBEAT_SECONDS + 10.0

    def sleep(seconds: float) -> None:
        clock.sleep(seconds)
        if clock.value >= released:
            theirs.release()

    with caplog.at_level(logging.WARNING):
        result = wait_for_turn(ours, timebase=Timebase(sleep=sleep, now=clock.now))

    heartbeats = [r for r in caplog.records if "still waiting" in r.message]
    assert len(heartbeats) == 3
    assert all(r.levelname == "WARNING" for r in heartbeats)
    assert result.blocked_by == ("wake_alarm",)
    ours.release()


def test_the_wait_is_published_while_it_happens(tmp_path: Path) -> None:
    """A blocked process cannot answer for itself, so it must be observable."""
    theirs = make_arbiter("wake_alarm", RANK_WAKE_ALARM, tmp_path)
    ours = make_arbiter("screen_locker", RANK_SCREEN_LOCKER, tmp_path)
    clock = FakeClock()
    seen: list[tuple[tuple[str, ...], float]] = []

    def sleep(seconds: float) -> None:
        clock.sleep(seconds)
        if clock.value >= QUEUE_HEARTBEAT_SECONDS + 10.0:
            theirs.release()

    wait_for_turn(
        ours,
        on_state=lambda blocked, elapsed: seen.append((blocked, elapsed)),
        timebase=Timebase(sleep=sleep, now=clock.now),
    )

    # First sighting, then at least one heartbeat, then the clear.
    assert seen[0][0] == ("wake_alarm",)
    assert any(blocked == ("wake_alarm",) for blocked, _ in seen[1:-1])
    assert seen[-1][0] == ()
    ours.release()


def test_an_unblocked_wait_publishes_only_the_clear(tmp_path: Path) -> None:
    """The common case must not spam an observer that has nothing to show."""
    ours = make_arbiter("screen_locker", RANK_SCREEN_LOCKER, tmp_path)
    clock = FakeClock()
    seen: list[tuple[str, ...]] = []

    wait_for_turn(
        ours,
        on_state=lambda blocked, _elapsed: seen.append(blocked),
        timebase=Timebase(sleep=clock.sleep, now=clock.now),
    )

    assert seen == [()]
    ours.release()


def test_hitting_the_deadline_publishes_the_clear_too(tmp_path: Path) -> None:
    """Arming anyway must not leave an observer thinking we are still queued."""
    theirs = make_arbiter("wake_alarm", RANK_WAKE_ALARM, tmp_path)
    ours = make_arbiter("screen_locker", RANK_SCREEN_LOCKER, tmp_path)
    clock = FakeClock()
    seen: list[tuple[str, ...]] = []

    result = wait_for_turn(
        ours,
        poll=10.0,
        deadline=30.0,
        on_state=lambda blocked, _elapsed: seen.append(blocked),
        timebase=Timebase(sleep=clock.sleep, now=clock.now),
    )

    assert result.timed_out
    assert seen[-1] == ()
    theirs.release()
    ours.release()
