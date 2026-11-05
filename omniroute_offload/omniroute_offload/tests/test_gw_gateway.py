from __future__ import annotations

import runpy
import subprocess
import sys
import urllib.request
from typing import TYPE_CHECKING, Any

import pytest

from omniroute_offload import _gw_api as api
from omniroute_offload import _gw_combo as combo
from omniroute_offload import _gw_config as gwc
from omniroute_offload import _gw_docker as dock
from omniroute_offload import _gw_health as health
from omniroute_offload import _gw_update as update
from omniroute_offload import gateway

if TYPE_CHECKING:
    from pathlib import Path


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
    monkeypatch.delenv("OMNIROUTE_NAME", raising=False)
    monkeypatch.delenv("OMNIROUTE_PORT", raising=False)
    monkeypatch.delenv("OMNIROUTE_VOLUME", raising=False)
    (tmp_path / ".config/omniroute").mkdir(parents=True)
    (tmp_path / ".config/omniroute/admin_password").write_text("pw\n")


class Calls:
    def __init__(self) -> None:
        self.events: list[tuple[Any, ...]] = []


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> Calls:
    rec = Calls()

    def recreate(cfg: gwc.Config, image: str, password: str) -> None:
        rec.events.append(("recreate", cfg.name, image, password))

    monkeypatch.setattr(dock, "recreate", recreate)
    monkeypatch.setattr(health, "wait_up", lambda _cfg: True)
    return rec


def test_start_recreates_pinned_image_and_reports_url(
    calls: Calls, capsys: pytest.CaptureFixture[str]
) -> None:
    assert gateway.main(["start"]) == 0
    assert calls.events == [("recreate", "omniroute", gwc.DEFAULT_IMAGE, "pw")]
    assert "omniroute up: http://127.0.0.1:20128" in capsys.readouterr().out


def test_start_fails_when_api_never_comes_up(
    calls: Calls, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(health, "wait_up", lambda _cfg: False)
    assert gateway.main(["start"]) == 1
    assert "docker logs omniroute" in capsys.readouterr().err


def test_instance_comes_from_environment(
    calls: Calls, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMNIROUTE_NAME", "tetris")
    assert gateway.main(["start"]) == 0
    assert calls.events[0][1] == "tetris"


def test_backup_prints_path_with_image_tag_label(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    labels: list[str] = []

    def backup(_cfg: gwc.Config, label: str) -> Path:
        labels.append(label)
        return tmp_path / "x.tar.gz"

    monkeypatch.setattr(dock, "backup", backup)
    assert gateway.main(["backup"]) == 0
    assert labels == ["3.8.52-web"]
    assert capsys.readouterr().out.strip() == str(tmp_path / "x.tar.gz")


@pytest.mark.parametrize("code", [0, 1])
def test_combo_exit_code_follows_refresh(
    monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    monkeypatch.setattr(combo, "refresh", lambda _cfg: code == 0)
    assert gateway.main(["combo"]) == code


@pytest.mark.parametrize(
    ("command", "module"), [("health", health), ("update", update)]
)
def test_health_and_update_dispatch_and_propagate_exit_code(
    monkeypatch: pytest.MonkeyPatch, command: str, module: Any
) -> None:
    seen: list[str] = []

    def run(cfg: gwc.Config) -> int:
        seen.append(cfg.name)
        return 7

    monkeypatch.setattr(module, "run", run)
    assert gateway.main([command]) == 7
    assert seen == ["omniroute"]


@pytest.mark.parametrize(
    "error",
    [dock.DockerError("daemon down"), api.ApiError("refused"), OSError("no file")],
)
def test_known_errors_become_exit_1_with_message(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
) -> None:
    def boom(_cfg: gwc.Config) -> bool:
        raise error

    monkeypatch.setattr(combo, "refresh", boom)
    assert gateway.main(["combo"]) == 1
    assert f"omniroute-gateway combo: {error}" in capsys.readouterr().err


def test_unknown_command_is_rejected() -> None:
    with pytest.raises(SystemExit) as exc:
        gateway.main(["explode"])
    assert exc.value.code == 2


def test_main_reads_sys_argv_and_runs_as_script(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(combo, "refresh", lambda _cfg: True)
    monkeypatch.setattr(sys, "argv", ["omniroute-gateway", "combo"])
    assert gateway.main() == 0
    monkeypatch.delitem(sys.modules, "omniroute_offload.gateway")
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("omniroute_offload.gateway", run_name="__main__")
    assert exc.value.code == 0
