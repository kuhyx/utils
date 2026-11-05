from __future__ import annotations

import subprocess
import urllib.error
import urllib.request
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pytest

from omniroute_offload import _gw_api as api
from omniroute_offload import _gw_config as gwc
from omniroute_offload.tests.conftest import FakeResp

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


def test_call_get_has_no_body(net: Net) -> None:
    net.replies = [{"a": 1}]
    assert api.call("http://x/y", timeout=3) == {"a": 1}
    assert net.reqs[0].data is None
    assert net.reqs[0].get_method() == "GET"
    assert net.timeouts == [3]


def test_call_post_sends_json_and_headers(net: Net) -> None:
    net.replies = [{}]
    api.call("http://x/y", {"k": "v"}, headers={"authorization": "Bearer t"})
    req = net.reqs[0]
    assert req.get_method() == "POST"
    assert net.bodies() == [{"k": "v"}]
    assert req.get_header("Content-type") == "application/json"
    assert req.get_header("Authorization") == "Bearer t"


@pytest.mark.parametrize(
    "err",
    [urllib.error.URLError("refused"), TimeoutError("slow"), ConnectionResetError("x")],
)
def test_transport_errors_become_api_error(net: Net, err: BaseException) -> None:
    net.replies = [err]
    with pytest.raises(api.ApiError, match="http://x"):
        api.call("http://x")


def test_empty_body_is_empty_dict_but_non_json_is_an_error(net: Net) -> None:
    net.replies = [FakeResp(b""), FakeResp(b"<html>")]
    assert api.call("http://x") == {}
    with pytest.raises(api.ApiError, match="not JSON"):
        api.call("http://x")


def test_alive_true_and_false(cfg: gwc.Config, net: Net) -> None:
    net.replies = [{}, urllib.error.URLError("down")]
    assert api.alive(cfg) is True
    assert net.reqs[0].full_url == f"{cfg.base_url}/api/auth/status"
    assert net.timeouts == [5]
    assert api.alive(cfg) is False


def test_chat_returns_stripped_text_via_combo(cfg: gwc.Config, net: Net) -> None:
    net.replies = [{"choices": [{"message": {"content": " OK \n"}}]}]
    assert api.chat(cfg, "sekret") == "OK"
    req = net.reqs[0]
    assert req.full_url == f"{cfg.base_url}/v1/chat/completions"
    assert req.get_header("Authorization") == "Bearer sekret"
    assert net.bodies()[0]["model"] == api.COMBO
    assert net.timeouts == [api.CHAT_TIMEOUT_S]


@pytest.mark.parametrize(
    ("message", "match"),
    [
        ({}, "unexpected reply"),
        ({"choices": []}, "unexpected reply"),
        ({"choices": None}, "unexpected reply"),
        ({"choices": [{"message": {}}]}, "unexpected reply"),
        ({"choices": [{"message": {"content": None}}]}, "empty completion"),
        ({"choices": [{"message": {"content": "  "}}]}, "empty completion"),
    ],
)
def test_chat_bad_replies(
    cfg: gwc.Config, net: Net, message: object, match: str
) -> None:
    net.replies = [message]
    with pytest.raises(api.ApiError, match=match):
        api.chat(cfg, "k")


def test_cooldown_until_variants() -> None:
    top = "2026-11-05T10:00:00+00:00"
    late = "2026-11-05T12:00:00+00:00"
    assert api.cooldown_until({}) is None
    assert api.cooldown_until({"rateLimitedUntil": top}) == datetime(
        2026, 11, 5, 10, tzinfo=UTC
    )
    conn = {
        "rateLimitedUntil": top,
        "providerSpecificData": {
            "apiKeyHealth": {
                "k1": {"cooldownUntil": late},
                "k2": {"cooldownUntil": "garbage"},
                "k3": "not-a-dict",
                "k4": {"cooldownUntil": 5},
            }
        },
    }
    assert api.cooldown_until(conn) == datetime(2026, 11, 5, 12, tzinfo=UTC)
    assert api.cooldown_until({"rateLimitedUntil": "garbage"}) is None
    assert api.cooldown_until({"providerSpecificData": None}) is None
