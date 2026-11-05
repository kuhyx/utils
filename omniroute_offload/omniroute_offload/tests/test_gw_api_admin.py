from __future__ import annotations

import subprocess
import urllib.error
import urllib.request
from typing import TYPE_CHECKING, Any

import pytest

from omniroute_offload import _gw_api as api
from omniroute_offload import _gw_config as gwc

if TYPE_CHECKING:
    from pathlib import Path

    from omniroute_offload.tests.conftest import Net


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


@pytest.fixture
def admin(
    cfg: gwc.Config, net: Net, monkeypatch: pytest.MonkeyPatch
) -> tuple[api.Admin, Net]:
    seen: list[Any] = []

    def fake_build_opener(*handlers: Any) -> Net:
        seen.extend(handlers)
        return net

    monkeypatch.setattr(urllib.request, "build_opener", fake_build_opener)
    net.replies = [{"ok": True}]
    adm = api.Admin(cfg, "pw")
    assert len(seen) == 1
    assert net.reqs[0].full_url == f"{cfg.base_url}/api/auth/login"
    assert net.bodies() == [{"password": "pw"}]
    return adm, net


def test_admin_login_refused(
    cfg: gwc.Config, net: Net, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(urllib.request, "build_opener", lambda *_h: net)
    net.replies = [urllib.error.URLError("401")]
    with pytest.raises(api.ApiError):
        api.Admin(cfg, "bad")


def test_providers_shapes(admin: tuple[api.Admin, Net]) -> None:
    adm, net = admin
    conns = [{"id": "1"}, {"id": "2"}]
    net.replies = [{"connections": conns}, conns]
    assert adm.providers() == conns
    assert adm.providers() == conns
    assert net.reqs[-1].full_url.endswith("/api/providers")


def test_combo_members_filters_by_name_and_falls_back_to_model_prefix(
    admin: tuple[api.Admin, Net],
) -> None:
    adm, net = admin
    combos = [
        {
            "name": "free-best",
            "models": [
                {"providerId": "nvidia", "model": "nvidia/a"},
                {"model": "groq/b"},
                "not-a-dict",
            ],
        },
        {"name": "other", "models": [{"providerId": "zzz"}]},
    ]
    net.replies = [{"combos": combos}, combos]
    assert adm.combo_members() == {"nvidia", "groq"}
    assert adm.combo_members() == {"nvidia", "groq"}
    net.replies = [{"combos": []}]
    assert adm.combo_members("free-best") == set()


def test_reactivate_puts_active(admin: tuple[api.Admin, Net]) -> None:
    adm, net = admin
    net.replies = [{}]
    adm.reactivate("abc")
    req = net.reqs[-1]
    assert req.get_method() == "PUT"
    assert req.full_url.endswith("/api/providers/abc")
    assert net.bodies()[-1] == {"testStatus": "active"}


def test_upsert_combo_updates_existing(admin: tuple[api.Admin, Net]) -> None:
    adm, net = admin
    net.replies = [{"combos": [{"id": "c1", "name": "free-best"}]}, {}]
    adm.upsert_combo("free-best", ["a/x", "b/y"])
    req = net.reqs[-1]
    assert req.get_method() == "PUT"
    assert req.full_url.endswith("/api/combos/c1")
    assert net.bodies()[-1] == {
        "name": "free-best",
        "models": ["a/x", "b/y"],
        "strategy": "priority",
    }


def test_upsert_combo_creates_when_missing(admin: tuple[api.Admin, Net]) -> None:
    adm, net = admin
    net.replies = [[{"id": "c9", "name": "other"}], {}]
    adm.upsert_combo("free-best", ["a/x"])
    req = net.reqs[-1]
    assert req.get_method() == "POST"
    assert req.full_url.endswith("/api/combos")
    assert net.bodies()[-1]["name"] == "free-best"
