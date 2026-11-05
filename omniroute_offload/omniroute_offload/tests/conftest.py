"""Opt-in fake gateway world shared by the health tests (no autouse fixtures)."""

from __future__ import annotations

import io
import json
import urllib.request
from typing import TYPE_CHECKING, Any, Self

import pytest

from omniroute_offload import _gw_api as api
from omniroute_offload import _gw_config as gwc
from omniroute_offload import _gw_docker as dock
from omniroute_offload import _gw_health as health
from omniroute_offload import _gw_notify as note

if TYPE_CHECKING:
    from pathlib import Path


class World:
    """Fake docker + gateway; every side effect lands in `events`/`notices`."""

    def __init__(self) -> None:
        self.status: str | None = "running"
        self.alive = True
        self.chat_ok = True
        self.conns: list[dict[str, Any]] = []
        self.members = {"p"}
        self.admin_error: Exception | None = None
        self.restart_fixes = True
        self.restart_error: Exception | None = None
        self.heal_by_reactivate = False
        self.notify_ok = True
        self.events: list[str] = []
        self.notices: list[tuple[str, str]] = []

    @staticmethod
    def conn(cid: str, **over: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "id": cid, "provider": "p", "isActive": True, "testStatus": "active",
        }  # fmt: skip
        return base | over

    def chat(self, _cfg: gwc.Config, key: str) -> str:
        assert key == "key"
        if not self.chat_ok:
            msg = "503 all providers failed"
            raise api.ApiError(msg)
        return "OK"

    def admin(self, _cfg: gwc.Config, pw: str) -> World:
        assert pw == "pw"
        if self.admin_error:
            raise self.admin_error
        return self

    def providers(self) -> list[dict[str, Any]]:
        return self.conns

    def combo_members(self) -> set[str]:
        return self.members

    def reactivate(self, conn_id: str) -> None:
        self.events.append(f"reactivate:{conn_id}")
        self.chat_ok = self.chat_ok or self.heal_by_reactivate

    def _bring_up(self, event: str) -> None:
        self.events.append(event)
        if self.restart_error:
            raise self.restart_error
        if self.restart_fixes:
            self.status, self.alive = "running", True

    def restart(self, _cfg: gwc.Config) -> None:
        self._bring_up("restart")

    def recreate(self, _cfg: gwc.Config, image: str, password: str) -> None:
        assert (image, password) == (gwc.DEFAULT_IMAGE, "pw")
        self._bring_up("recreate")

    def notify(self, _cfg: gwc.Config, text: str, *, urgency: str = "normal") -> bool:
        self.notices.append((urgency, text))
        return self.notify_ok


@pytest.fixture
def health_cfg(tmp_path: Path) -> gwc.Config:
    made = gwc.Config.from_env({"HOME": str(tmp_path)})
    made.conf_dir.mkdir(parents=True)
    (made.conf_dir / "api_key").write_text("key\n")
    (made.conf_dir / "admin_password").write_text("pw\n")
    return made


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> World:
    w = World()
    monkeypatch.setattr(api, "alive", lambda _cfg: w.alive)
    monkeypatch.setattr(api, "chat", w.chat)
    monkeypatch.setattr(api, "Admin", w.admin)
    monkeypatch.setattr(dock, "status", lambda _cfg: w.status)
    monkeypatch.setattr(dock, "restart", w.restart)
    monkeypatch.setattr(dock, "recreate", w.recreate)
    monkeypatch.setattr(note, "notify", w.notify)
    monkeypatch.setattr(health, "wait_up", lambda _cfg, seconds=90: True)
    return w


class FakeResp(io.BytesIO):
    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def _resp(payload: object) -> FakeResp:
    return FakeResp(json.dumps(payload).encode())


class Net:
    """Records requests and replays queued replies (or raises queued errors)."""

    def __init__(self) -> None:
        self.reqs: list[urllib.request.Request] = []
        self.replies: list[Any] = []
        self.timeouts: list[float] = []

    def open(self, req: urllib.request.Request, timeout: float) -> FakeResp:
        self.reqs.append(req)
        self.timeouts.append(timeout)
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return reply if isinstance(reply, FakeResp) else _resp(reply)

    def bodies(self) -> list[Any]:
        out: list[Any] = []
        for req in self.reqs:
            assert req.data is None or isinstance(req.data, bytes)
            out.append(json.loads(req.data) if req.data else None)
        return out


@pytest.fixture
def net(monkeypatch: pytest.MonkeyPatch) -> Net:
    fake = Net()
    monkeypatch.setattr(urllib.request, "urlopen", fake.open)
    return fake
