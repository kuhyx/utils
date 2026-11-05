from __future__ import annotations

import subprocess
import urllib.request
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import pytest

from omniroute_offload import _gw_config as gwc
from omniroute_offload import _gw_docker as dock
from omniroute_offload import _gw_health as health

if TYPE_CHECKING:
    from pathlib import Path

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


def test_report_ok_recovery_clears_down_since(
    health_cfg: gwc.Config, world: World
) -> None:
    ok = health.Verdict("ok", "")
    assert health._report(health_cfg, {}, ok, NOW) == 0
    assert world.notices == []
    state: dict[str, Any] = {"down_since": "t"}
    assert health._report(health_cfg, state, ok, NOW) == 0
    assert state == {}
    assert world.notices == [("low", "recovered: free-best answers again")]


def test_report_degraded_notifies_once_per_day(
    health_cfg: gwc.Config, world: World
) -> None:
    verdict = health.Verdict("degraded", "all 2 combo providers cooling down")
    state: dict[str, Any] = {}
    assert health._report(health_cfg, state, verdict, NOW) == 0
    assert health._report(health_cfg, state, verdict, NOW + timedelta(hours=1)) == 0
    assert [u for u, _ in world.notices] == ["low"]
    assert health._report(health_cfg, state, verdict, NOW + timedelta(days=1)) == 0
    assert len(world.notices) == 2


def test_report_failed_alert_exits_1(health_cfg: gwc.Config, world: World) -> None:
    world.notify_ok = False
    state: dict[str, Any] = {"down_since": "t"}
    assert health._report(health_cfg, state, health.Verdict("ok", ""), NOW) == 1
    assert [u for u, _ in world.notices] == ["low"]
    degraded = health.Verdict("degraded", "all cooling")
    assert health._report(health_cfg, state, degraded, NOW) == 1
    assert [u for u, _ in world.notices] == ["low", "low"]
    # same day again: nothing is sent, so nothing can fail
    assert health._report(health_cfg, state, degraded, NOW) == 0
    assert len(world.notices) == 2


def test_report_down_notifies_once_per_outage(
    health_cfg: gwc.Config, world: World
) -> None:
    verdict = health.Verdict("down", "boom")
    state: dict[str, Any] = {}
    assert health._report(health_cfg, state, verdict, NOW) == 1
    assert health._report(health_cfg, state, verdict, NOW + timedelta(hours=1)) == 1
    assert world.notices == [("critical", "DOWN after auto-fix: boom")]
    assert state["down_since"] == NOW.isoformat()


def test_run_skips_when_lock_held(health_cfg: gwc.Config, world: World) -> None:
    with gwc.locked(health_cfg, blocking=True):
        assert health.run(health_cfg, NOW) == 0
    assert world.events == []
    assert world.notices == []


def test_run_healthy_uses_current_time_and_stays_quiet(
    health_cfg: gwc.Config, world: World
) -> None:
    assert health.run(health_cfg) == 0
    assert world.notices == []


def test_run_dead_container_is_fixed_without_alert(
    health_cfg: gwc.Config, world: World
) -> None:
    world.status, world.alive = "exited", False
    assert health.run(health_cfg, NOW) == 0
    assert world.events == ["restart"]
    assert world.notices == []
    assert gwc.load_state(health_cfg)["last_restart"] == NOW.isoformat()


def test_run_missing_container_is_recreated(
    health_cfg: gwc.Config, world: World
) -> None:
    world.status, world.alive = None, False
    assert health.run(health_cfg, NOW) == 0
    assert world.events == ["recreate"]


def test_run_second_restart_within_gap_stays_down_and_alerts_once(
    health_cfg: gwc.Config, world: World
) -> None:
    world.status, world.alive = "exited", False
    gwc.save_state(
        health_cfg, {"last_restart": (NOW - timedelta(minutes=5)).isoformat()}
    )
    assert health.run(health_cfg, NOW) == 1
    assert world.events == []
    assert [u for u, _ in world.notices] == ["critical"]
    assert health.run(health_cfg, NOW + timedelta(minutes=10)) == 1
    assert len(world.notices) == 1


def test_run_outage_then_recovery_cycle(health_cfg: gwc.Config, world: World) -> None:
    world.alive, world.restart_fixes = False, False
    assert health.run(health_cfg, NOW) == 1
    assert gwc.load_state(health_cfg)["down_since"] == NOW.isoformat()
    world.alive = True
    assert health.run(health_cfg, NOW + timedelta(hours=1)) == 0
    assert "down_since" not in gwc.load_state(health_cfg)
    assert [u for u, _ in world.notices] == ["critical", "low"]


def test_run_degraded_exit_zero_no_restart_one_notice(
    health_cfg: gwc.Config, world: World
) -> None:
    world.chat_ok = False
    world.conns = [world.conn("1", rateLimitedUntil=FUTURE)]
    assert health.run(health_cfg, NOW) == 0
    assert health.run(health_cfg, NOW + timedelta(minutes=10)) == 0
    assert world.events == []
    assert [u for u, _ in world.notices] == ["low"]


def test_run_reactivates_only_ended_cooldowns_and_never_restarts(
    health_cfg: gwc.Config, world: World
) -> None:
    world.chat_ok, world.heal_by_reactivate = False, True
    world.conns = [
        world.conn("a", testStatus="error", rateLimitedUntil=PAST),
        world.conn("b", provider="outsider", testStatus="error"),
    ]
    assert health.run(health_cfg, NOW) == 0
    assert world.events == ["reactivate:a"]


def test_run_ladder_failure_becomes_down(health_cfg: gwc.Config, world: World) -> None:
    msg = "docker restart failed: daemon gone"
    world.restart_error = dock.DockerError(msg)
    world.status, world.chat_ok = "exited", False
    assert health.run(health_cfg, NOW) == 1
    assert "fix ladder failed" in world.notices[0][1]
