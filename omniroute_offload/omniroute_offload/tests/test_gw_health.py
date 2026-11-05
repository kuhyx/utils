from __future__ import annotations

import subprocess
import time
import urllib.request
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import pytest

from omniroute_offload import _gw_api as api
from omniroute_offload import _gw_health as health

if TYPE_CHECKING:
    from pathlib import Path

    from omniroute_offload import _gw_config as gwc
    from omniroute_offload.tests.conftest import World

NOW = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
PAST = (NOW - timedelta(hours=1)).isoformat()
FUTURE = (NOW + timedelta(hours=1)).isoformat()


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def blocked(*_args: Any, **_kwargs: Any) -> Any:
        msg = "real process/network access is blocked in tests"
        raise AssertionError(msg)

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(subprocess, "run", blocked)
    monkeypatch.setattr(subprocess, "Popen", blocked)
    monkeypatch.setattr(urllib.request, "urlopen", blocked)
    monkeypatch.setattr(urllib.request, "build_opener", blocked)


class Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    fake = Clock()
    monkeypatch.setattr(time, "monotonic", fake.monotonic)
    monkeypatch.setattr(time, "sleep", fake.sleep)
    return fake


def test_secret_is_stripped(health_cfg: gwc.Config) -> None:
    assert health.secret(health_cfg, "api_key") == "key"


def test_wait_up_returns_at_once_when_alive(
    health_cfg: gwc.Config, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(api, "alive", lambda _cfg: True)
    assert health.wait_up(health_cfg) is True
    assert clock.sleeps == []


def test_wait_up_polls_every_two_seconds_until_alive(
    health_cfg: gwc.Config, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    answers = iter([False, False, True])
    monkeypatch.setattr(api, "alive", lambda _cfg: next(answers))
    assert health.wait_up(health_cfg) is True
    assert clock.sleeps == [2, 2]


def test_wait_up_gives_up_after_deadline(
    health_cfg: gwc.Config, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(api, "alive", lambda _cfg: False)
    assert health.wait_up(health_cfg, seconds=5) is False
    assert clock.sleeps == [2, 2, 2]


def test_check_down_when_api_dead(health_cfg: gwc.Config, world: World) -> None:
    world.alive = False
    verdict = health.check(health_cfg, NOW)
    assert verdict == health.Verdict("down", "API not answering")


def test_check_ok_on_real_chat(health_cfg: gwc.Config, world: World) -> None:
    assert health.check(health_cfg, NOW).state == "ok"


def test_check_degraded_only_when_all_active_members_cool(
    health_cfg: gwc.Config, world: World
) -> None:
    world.chat_ok = False
    world.conns = [
        world.conn("1", rateLimitedUntil=FUTURE),
        world.conn("2", rateLimitedUntil=FUTURE),
        world.conn("3", provider="outsider"),
        world.conn("4", isActive=False),
    ]
    verdict = health.check(health_cfg, NOW)
    assert verdict.state == "degraded"
    assert "all 2" in verdict.detail
    world.conns.append(world.conn("5", rateLimitedUntil=PAST))
    assert health.check(health_cfg, NOW).state == "down"


def test_check_down_without_member_connections(
    health_cfg: gwc.Config, world: World
) -> None:
    world.chat_ok = False
    world.conns = [world.conn("3", provider="outsider")]
    verdict = health.check(health_cfg, NOW)
    assert verdict == health.Verdict("down", "chat failed: 503 all providers failed")


def test_check_admin_failure_is_down_with_both_reasons(
    health_cfg: gwc.Config, world: World
) -> None:
    world.chat_ok = False
    world.admin_error = api.ApiError("login refused")
    verdict = health.check(health_cfg, NOW)
    assert verdict.state == "down"
    assert "chat failed" in verdict.detail
    assert "admin API: login refused" in verdict.detail


def test_check_missing_key_file_counts_as_chat_failure(
    health_cfg: gwc.Config, world: World
) -> None:
    (health_cfg.conf_dir / "api_key").unlink()
    (health_cfg.conf_dir / "admin_password").unlink()
    verdict = health.check(health_cfg, NOW)
    assert verdict.state == "down"
    assert "admin API" in verdict.detail


def test_restart_proceeds_on_corrupt_last_restart(
    health_cfg: gwc.Config, world: World
) -> None:
    state = {"last_restart": "not-a-date"}
    health._restart(health_cfg, state, NOW)
    assert world.events == ["restart"]
    assert state["last_restart"] == NOW.isoformat()


def test_restart_respects_gap_then_proceeds(
    health_cfg: gwc.Config, world: World
) -> None:
    last = (NOW - timedelta(minutes=29)).isoformat()
    recent = {"last_restart": last}
    health._restart(health_cfg, recent, NOW)
    assert world.events == []
    assert recent["last_restart"] == last
    old = {"last_restart": (NOW - timedelta(minutes=31)).isoformat()}
    health._restart(health_cfg, old, NOW)
    assert world.events == ["restart"]
    assert old["last_restart"] == NOW.isoformat()


def test_restart_recreates_missing_container(
    health_cfg: gwc.Config, world: World
) -> None:
    world.status = None
    state: dict[str, Any] = {}
    health._restart(health_cfg, state, NOW)
    assert world.events == ["recreate"]
    assert state["last_restart"] == NOW.isoformat()


def test_reactivate_only_stuck_combo_members_with_ended_cooldown(
    health_cfg: gwc.Config, world: World
) -> None:
    conn = world.conn
    world.conns = [
        conn("ok"),
        conn("cooling", testStatus="error", rateLimitedUntil=FUTURE),
        conn("stuck", testStatus="error", rateLimitedUntil=PAST),
        conn("stuck2", testStatus="unavailable"),
        conn("outsider", provider="other", testStatus="error"),
        conn("off", isActive=False, testStatus="error"),
    ]
    assert health._reactivate(health_cfg, NOW) == 2
    assert world.events == ["reactivate:stuck", "reactivate:stuck2"]


def test_heal_ok_touches_nothing(health_cfg: gwc.Config, world: World) -> None:
    assert health.heal(health_cfg, {}, NOW).state == "ok"
    assert world.events == []


@pytest.mark.parametrize("status", ["exited", None])
def test_heal_restarts_dead_container_then_rechecks(
    health_cfg: gwc.Config, world: World, status: str | None
) -> None:
    world.status, world.alive = status, False
    assert health.heal(health_cfg, {}, NOW).state == "ok"
    assert world.events == ["restart" if status else "recreate"]


def test_heal_restarts_running_container_with_dead_api(
    health_cfg: gwc.Config, world: World
) -> None:
    world.alive, world.restart_fixes = False, False
    assert health.heal(health_cfg, {}, NOW).state == "down"
    assert world.events == ["restart"]


def test_heal_reactivates_instead_of_restarting_when_container_is_fine(
    health_cfg: gwc.Config, world: World
) -> None:
    world.chat_ok, world.heal_by_reactivate = False, True
    world.conns = [world.conn("1", testStatus="error", rateLimitedUntil=PAST)]
    assert health.heal(health_cfg, {}, NOW).state == "ok"
    assert world.events == ["reactivate:1"]


def test_heal_stays_down_when_nothing_to_reactivate(
    health_cfg: gwc.Config, world: World
) -> None:
    world.chat_ok = False
    world.conns = [world.conn("1")]
    assert health.heal(health_cfg, {}, NOW).state == "down"
    assert world.events == []
