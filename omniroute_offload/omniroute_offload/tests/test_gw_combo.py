from __future__ import annotations

import subprocess
import urllib.request
from typing import TYPE_CHECKING, Any

import pytest

from omniroute_offload import _gw_api as api
from omniroute_offload import _gw_combo as combo
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


HEADER = "model\ttools\ttetris\tmax_prompt\n"


@pytest.fixture
def cfg(tmp_path: Path) -> gwc.Config:
    made = gwc.Config.from_env({"HOME": str(tmp_path)})
    made.conf_dir.mkdir(parents=True)
    (made.conf_dir / "admin_password").write_text("pw\n")
    return made


class FakeAdmin:
    def __init__(self, cfg: gwc.Config, password: str) -> None:
        self.pw = password
        self.upserts: list[tuple[str, list[str]]] = []

    def upsert_combo(self, name: str, models: list[str]) -> None:
        self.upserts.append((name, models))


@pytest.fixture
def admins(monkeypatch: pytest.MonkeyPatch) -> list[FakeAdmin]:
    made: list[FakeAdmin] = []

    def factory(cfg: gwc.Config, password: str) -> FakeAdmin:
        made.append(FakeAdmin(cfg, password))
        return made[-1]

    monkeypatch.setattr(api, "Admin", factory)
    return made


def _write(cfg: gwc.Config, body: str) -> None:
    (cfg.conf_dir / "order.tsv").write_text(body)


def test_ranked_models_applies_every_filter_and_keeps_order(tmp_path: Path) -> None:
    order = tmp_path / "order.tsv"
    order.write_text(
        HEADER
        + "z/best\tyes\t1.0\t128000\n"
        + "a/no-tools\tno\t1.0\t128000\n"
        + "a/no-tetris\tyes\t-\t128000\n"
        + "a/low-tetris\tyes\t0.84\t128000\n"
        + "a/exact\tyes\t0.85\t16000\n"
        + "a/small-window\tyes\t0.9\t15999\n"
        + "a/no-window\tyes\t0.9\t\n"
        + "b/second\tyes\t0.9\t32000\n"
    )
    assert combo.ranked_models(order) == ["z/best", "a/exact", "b/second"]


def test_ranked_models_without_tetris_column_keeps_nothing(tmp_path: Path) -> None:
    order = tmp_path / "order.tsv"
    order.write_text("model\ttools\tmax_prompt\na/b\tyes\t99999\n")
    assert combo.ranked_models(order) == []


def test_refresh_upserts_filtered_combo(
    cfg: gwc.Config, admins: list[FakeAdmin], capsys: pytest.CaptureFixture[str]
) -> None:
    _write(cfg, HEADER + "x/one\tyes\t0.9\t20000\nx/two\tno\t0.9\t20000\n")
    assert combo.refresh(cfg) is True
    assert admins[0].pw == "pw"
    assert admins[0].upserts == [(api.COMBO, ["x/one"])]
    assert "free-best: x/one" in capsys.readouterr().err


def test_refresh_keeps_combo_when_order_missing(
    cfg: gwc.Config, admins: list[FakeAdmin], capsys: pytest.CaptureFixture[str]
) -> None:
    assert combo.refresh(cfg) is False
    assert admins == []
    assert "combo kept: no" in capsys.readouterr().err


@pytest.mark.parametrize(
    "body",
    ["", HEADER, HEADER + "x/one\tno\t0.9\t20000\n"],
    ids=["empty", "header", "none"],
)
def test_refresh_keeps_combo_when_nothing_passes(
    cfg: gwc.Config,
    admins: list[FakeAdmin],
    capsys: pytest.CaptureFixture[str],
    body: str,
) -> None:
    _write(cfg, body)
    assert combo.refresh(cfg) is False
    assert admins == []
    assert "passes the filter" in capsys.readouterr().err
