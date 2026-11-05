from __future__ import annotations

import subprocess
import urllib.request
from typing import TYPE_CHECKING, Any

import pytest

from omniroute_offload import _gw_config as gwc

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


@pytest.fixture
def cfg(tmp_path: Path) -> gwc.Config:
    return gwc.Config.from_env({"HOME": str(tmp_path)})


def test_from_env_defaults(cfg: gwc.Config, tmp_path: Path) -> None:
    assert cfg.name == "omniroute"
    assert cfg.volume == "omniroute-data"
    assert cfg.port == 20128
    assert cfg.base_url == "http://127.0.0.1:20128"
    assert cfg.conf_dir == tmp_path / ".config/omniroute"
    assert cfg.state_dir == tmp_path / ".local/state/omniroute-gateway/omniroute"
    assert cfg.backup_dir == tmp_path / "data/backups/omniroute/omniroute"
    assert cfg.signal_env == tmp_path / "src/signal-bot/.env"


def test_from_env_overrides(tmp_path: Path) -> None:
    cfg = gwc.Config.from_env(
        {
            "HOME": str(tmp_path),
            "OMNIROUTE_NAME": "tetris",
            "OMNIROUTE_VOLUME": "t-data",
            "OMNIROUTE_PORT": "20999",
            "OMNIROUTE_SIGNAL_ENV": "/x/signal.env",
        }
    )
    assert (cfg.name, cfg.volume, cfg.port) == ("tetris", "t-data", 20999)
    assert cfg.base_url == "http://127.0.0.1:20999"
    assert cfg.state_dir == tmp_path / ".local/state/omniroute-gateway/tetris"
    assert cfg.backup_dir == tmp_path / "data/backups/omniroute/tetris"
    assert str(cfg.signal_env) == "/x/signal.env"


def test_from_env_reads_process_env_and_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OMNIROUTE_NAME", "fromproc")
    assert gwc.Config.from_env().state_dir.parts[-1] == "fromproc"
    assert gwc.Config.from_env({}).conf_dir == tmp_path / ".config/omniroute"


def test_image_default_pinned_and_empty(cfg: gwc.Config) -> None:
    assert cfg.image() == gwc.DEFAULT_IMAGE
    cfg.state_dir.mkdir(parents=True)
    (cfg.state_dir / "image").write_text("   \n")
    assert cfg.image() == gwc.DEFAULT_IMAGE
    (cfg.state_dir / "image").write_text("repo:9.9.9-web\n")
    assert cfg.image() == "repo:9.9.9-web"


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("3.8.52-web", (3, 8, 52)),
        ("diegosouzapw/omniroute:3.10.0-web", (3, 10, 0)),
        ("latest", None),
        ("3.8.52", None),
        ("3.8.52-rc1-web", None),
        ("repo:3.8-web", None),
    ],
)
def test_version(tag: str, expected: tuple[int, int, int] | None) -> None:
    assert gwc.version(tag) == expected


def test_locked_blocking_yields_true_and_creates_state_dir(cfg: gwc.Config) -> None:
    with gwc.locked(cfg, blocking=True) as got:
        assert got is True
        assert (cfg.state_dir / "lock").exists()


def test_locked_nonblocking_yields_false_while_held(cfg: gwc.Config) -> None:
    with gwc.locked(cfg, blocking=True), gwc.locked(cfg, blocking=False) as got:
        assert got is False
    with gwc.locked(cfg, blocking=False) as got:
        assert got is True


def test_load_state_missing_invalid_and_non_dict(cfg: gwc.Config) -> None:
    assert gwc.load_state(cfg) == {}
    cfg.state_dir.mkdir(parents=True)
    alert = cfg.state_dir / "alert.json"
    alert.write_text("{not json")
    assert gwc.load_state(cfg) == {}
    alert.write_text("[1, 2]")
    assert gwc.load_state(cfg) == {}
    alert.write_text('{"down_since": "t"}')
    assert gwc.load_state(cfg) == {"down_since": "t"}


def test_save_state_roundtrip_and_image_pin(cfg: gwc.Config) -> None:
    gwc.save_state(cfg, {"b": 1, "a": 2})
    assert gwc.load_state(cfg) == {"a": 2, "b": 1}
    assert not (cfg.state_dir / "image").exists()
    gwc.save_state(cfg, {}, image="repo:3.9.0-web")
    assert (cfg.state_dir / "image").read_text() == "repo:3.9.0-web\n"
    assert cfg.image() == "repo:3.9.0-web"
