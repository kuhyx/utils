from __future__ import annotations

import subprocess
import urllib.request
from typing import TYPE_CHECKING, Any

import pytest

from omniroute_offload import _gw_api as api
from omniroute_offload import _gw_combo as combo
from omniroute_offload import _gw_config as gwc
from omniroute_offload import _gw_docker as dock
from omniroute_offload import _gw_health as health
from omniroute_offload import _gw_notify as note
from omniroute_offload import _gw_update as update

if TYPE_CHECKING:
    from pathlib import Path

OLD = gwc.DEFAULT_IMAGE
NEW = f"{gwc.REPO}:3.9.0-web"


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


@pytest.fixture
def cfg(tmp_path: Path) -> gwc.Config:
    made = gwc.Config.from_env({"HOME": str(tmp_path)})
    made.conf_dir.mkdir(parents=True)
    (made.conf_dir / "admin_password").write_text("pw\n")
    return made


class Ops:
    """Fake docker/health/notify layer; `events` keeps the order of side effects."""

    def __init__(self, archive: Path) -> None:
        self.archive = archive
        self.events: list[tuple[str, ...]] = []
        self.notices: list[tuple[str, str]] = []
        self.latest = NEW
        self.verdict = health.Verdict("ok", "chat answered")
        self.up = True
        self.errors: dict[str, Exception] = {}
        self.container: str | None = "running"
        self.notify_ok = True

    def _step(self, name: str, *detail: str) -> None:
        self.events.append((name, *detail))
        if name in self.errors:
            raise self.errors[name]

    def backup(self, _cfg: gwc.Config, label: str) -> Path:
        self._step("backup", label)
        return self.archive

    def latest_image(self) -> str:
        self._step("latest")
        return self.latest

    def pull(self, image: str) -> None:
        self._step("pull", image)

    def recreate(self, _cfg: gwc.Config, image: str, pw: str) -> None:
        assert pw == "pw"
        self._step("recreate", image)

    def status(self, _cfg: gwc.Config) -> str | None:
        self._step("status")
        return self.container

    def docker(self, *args: str, timeout: float = 120) -> str:
        self._step("docker", *args)
        return ""

    def restore(self, _cfg: gwc.Config, image: str, archive: Path) -> None:
        assert archive == self.archive
        self._step("restore", image)

    def wait_up(self, _cfg: gwc.Config, seconds: float = 90) -> bool:
        self._step("wait_up")
        return self.up

    def check(self, _cfg: gwc.Config, _now: object) -> health.Verdict:
        self._step("check")
        return self.verdict

    def refresh(self, _cfg: gwc.Config) -> bool:
        self._step("combo")
        return True

    def notify(self, _cfg: gwc.Config, text: str, *, urgency: str = "normal") -> bool:
        self.notices.append((urgency, text))
        return self.notify_ok

    def names(self) -> list[str]:
        return [e[0] for e in self.events]


@pytest.fixture
def ops(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Ops:
    o = Ops(tmp_path / "backup.tar.gz")
    monkeypatch.setattr(dock, "backup", o.backup)
    monkeypatch.setattr(update, "latest_image", o.latest_image)
    monkeypatch.setattr(dock, "pull", o.pull)
    monkeypatch.setattr(dock, "recreate", o.recreate)
    monkeypatch.setattr(dock, "docker", o.docker)
    monkeypatch.setattr(dock, "status", o.status)
    monkeypatch.setattr(dock, "restore", o.restore)
    monkeypatch.setattr(health, "wait_up", o.wait_up)
    monkeypatch.setattr(health, "check", o.check)
    monkeypatch.setattr(combo, "refresh", o.refresh)
    monkeypatch.setattr(note, "notify", o.notify)
    return o


def test_latest_image_picks_highest_stable_web_tag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    names = ["3.9.0-web", "3.10.1-web", "3.11.0-rc1-web", "latest", "3.8.52-web"]
    seen: list[str] = []

    def fake_call(url: str, *, timeout: float) -> Any:
        seen.append(url)
        return {"results": [{"name": n} for n in names] + [{}]}

    monkeypatch.setattr(api, "call", fake_call)
    assert update.latest_image() == f"{gwc.REPO}:3.10.1-web"
    assert seen == [update.HUB]


def test_latest_image_without_stable_tag_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api, "call", lambda *_a, **_k: {"results": [{"name": "dev"}]})
    with pytest.raises(api.ApiError, match="no stable"):
        update.latest_image()


@pytest.mark.parametrize("latest", [OLD, f"{gwc.REPO}:3.8.1-web"])
def test_up_to_date_changes_nothing(cfg: gwc.Config, ops: Ops, latest: str) -> None:
    ops.latest = latest
    assert update.run(cfg) == 0
    assert ops.names() == ["backup", "latest"]
    assert ops.events[0] == ("backup", "3.8.52-web")
    assert ops.notices == []
    assert not (cfg.state_dir / "image").exists()


def test_unparseable_pinned_image_is_left_alone(cfg: gwc.Config, ops: Ops) -> None:
    gwc.save_state(cfg, {}, image="repo:latest")
    assert update.run(cfg) == 0
    assert ops.names() == ["backup", "latest"]


def test_success_pins_image_refreshes_combo_and_notifies(
    cfg: gwc.Config, ops: Ops
) -> None:
    gwc.save_state(cfg, {"last_restart": "t"})
    assert update.run(cfg) == 0
    assert ops.names() == [
        "backup",
        "latest",
        "pull",
        "recreate",
        "wait_up",
        "check",
        "combo",
    ]
    assert ("recreate", NEW) in ops.events
    assert cfg.image() == NEW
    assert gwc.load_state(cfg) == {"last_restart": "t"}
    assert ops.notices == [("low", f"updated {OLD} -> {NEW}")]


def test_unsent_success_notice_exits_1_but_keeps_the_update(
    cfg: gwc.Config, ops: Ops
) -> None:
    ops.notify_ok = False
    assert update.run(cfg) == 1
    assert cfg.image() == NEW
    assert ops.names()[-1] == "combo"
    assert ops.notices == [("low", f"updated {OLD} -> {NEW}")]


def test_rollback_skips_stop_when_container_is_gone(cfg: gwc.Config, ops: Ops) -> None:
    ops.verdict = health.Verdict("down", "boom")
    ops.container = None
    assert update.run(cfg) == 1
    tail = ops.events[ops.names().index("status") :]
    assert tail == [("status",), ("restore", OLD), ("recreate", OLD), ("wait_up",)]
    assert ("docker", "stop", "-t", "40", cfg.name) not in ops.events


def test_failed_health_rolls_back_in_order_and_alerts(
    cfg: gwc.Config, ops: Ops
) -> None:
    ops.verdict = health.Verdict("down", "chat failed: 503")
    assert update.run(cfg) == 1
    assert ops.events[-6:] == [
        ("check",),
        ("status",),
        ("docker", "stop", "-t", "40", cfg.name),
        ("restore", OLD),
        ("recreate", OLD),
        ("wait_up",),
    ]
    assert cfg.image() == OLD
    assert "combo" not in ops.names()
    urgency, text = ops.notices[0]
    assert urgency == "critical"
    assert f"update to {NEW} failed (chat failed: 503); rolled back to {OLD}" == text


def test_api_never_up_rolls_back(cfg: gwc.Config, ops: Ops) -> None:
    ops.up = False
    assert update.run(cfg) == 1
    assert "check" not in ops.names()[: ops.names().index("restore")]
    assert "never came up" in ops.notices[0][1]
    assert ("restore", OLD) in ops.events


@pytest.mark.parametrize(
    "error",
    [dock.DockerError("pull denied"), api.ApiError("x"), OSError("disk")],
)
def test_pull_failure_rolls_back(cfg: gwc.Config, ops: Ops, error: Exception) -> None:
    ops.errors["pull"] = error
    assert update.run(cfg) == 1
    assert ("restore", OLD) in ops.events
    assert str(error) in ops.notices[0][1]


@pytest.mark.parametrize("step", ["backup", "latest"])
def test_job_failure_notifies_and_exits_1(cfg: gwc.Config, ops: Ops, step: str) -> None:
    ops.errors[step] = dock.DockerError("docker cp failed: boom")
    assert update.run(cfg) == 1
    assert "restore" not in ops.names()
    assert ops.notices == [("critical", "update job failed: docker cp failed: boom")]
