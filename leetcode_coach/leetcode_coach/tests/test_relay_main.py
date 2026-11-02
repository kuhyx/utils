"""The service entry point and the phone link's sign-in retries."""

from __future__ import annotations

import json
import signal
import threading
from typing import TYPE_CHECKING, Any

import crdt_sync

from leetcode_coach.relay import __main__ as entry
from leetcode_coach.relay import app as app_mod
from leetcode_coach.relay import config
from leetcode_coach.relay.rtdb import Rtdb
from leetcode_coach.tests import _relay_support as rs
from leetcode_coach.tests._fake_rtdb import FakeRtdb
from leetcode_guard import _snapshot_auth

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_make_rtdb_signs_in_as_its_own_app(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(config.RTDB_ENV, "")
    seen: list[str] = []

    class Auth:
        @staticmethod
        def id_token() -> str:
            return "live"

    class Client:
        auth = Auth()

    def connect(app: str, *, timeout_seconds: float) -> Client:
        seen.append(app)
        assert timeout_seconds == 15
        return Client()

    class Config:
        database_url = "https://db.example"

    monkeypatch.setattr(_snapshot_auth, "connect", connect)
    monkeypatch.setattr(crdt_sync.FirebaseConfig, "load", lambda _path: Config())
    rtdb = entry.make_rtdb()
    assert seen == ["leetcode_coach_relay"]
    assert rtdb.url("state").startswith("https://db.example/leetcode-guard/coach/")


def test_main_serves_until_sigterm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rs.fake_claude(tmp_path, monkeypatch, haiku=[], coach=[])
    handlers: dict[int, Any] = {}
    monkeypatch.setattr(signal, "signal", handlers.setdefault)
    monkeypatch.setenv(config.DIR_ENV, str(tmp_path / "relay"))
    monkeypatch.setenv(config.PORT_ENV, "0")
    with FakeRtdb.start() as fake:
        monkeypatch.setenv(config.RTDB_ENV, fake.url)
        result: list[int] = []
        runner = threading.Thread(target=lambda: result.append(entry.main()))
        runner.start()
        rs.wait_for(lambda: fake.read("state"))
        assert json.loads(fake.read("state"))["session"] is None
        assert fake.tokens[-1] == entry.FAKE_ID
        rs.wait_for(lambda: signal.SIGTERM in handlers)
        handlers[signal.SIGTERM](signal.SIGTERM, None)
        runner.join(timeout=10)
    assert result == [0]
    assert signal.SIGINT in handlers


def test_connect_phone_retries_until_it_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(app_mod, "CONNECT_BACKOFF_S", (0.0,))
    rig = rs.make_rig(tmp_path, start=False)
    with FakeRtdb.start() as fake:
        tries: list[int] = []

        def make() -> Rtdb:
            tries.append(1)
            if len(tries) < 3:
                msg = "INVALID_LOGIN_CREDENTIALS"
                raise RuntimeError(msg)
            return Rtdb(fake.url, lambda: "tok")

        rig.relay.connect_phone(make)
        assert len(tries) == 3
        assert rig.relay.phone is not None
        assert "phone path retries" in caplog.text
        rig.relay.stop()
    stopped = rs.make_rig(tmp_path / "b", start=False)
    stopped.relay.stop_event.set()
    stopped.relay.connect_phone(make)
    assert stopped.relay.phone is None
    stopped.relay.stop()
