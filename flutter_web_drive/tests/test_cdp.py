"""CDP session, target discovery and the headless safety check."""

from __future__ import annotations

import io
import json
from typing import Any

import pytest
import websocket

from flutter_web_drive import cdp
from flutter_web_drive.errors import EXIT_BROWSER, EXIT_UNSAFE, DriveError
from flutter_web_drive.tests.fakes import (
    HEADED,
    HEADLESS,
    PAGE_TARGETS,
    FakePage,
    FakeWs,
)


def _fetch(version: dict[str, Any] | None, targets: list[dict[str, Any]]) -> cdp.Fetch:
    def fetch(port: int, path: str) -> Any:
        if version is None:
            raise OSError("refused")
        return version if path == "/json/version" else targets

    return fetch


def test_call_returns_result_and_collects_events() -> None:
    ws = FakeWs(
        lambda m, p: {"result": {"ok": m}}, events=[{"method": "Log.entryAdded"}]
    )
    sess = cdp.Session(ws)
    assert sess.call("Log.enable") == {"ok": "Log.enable"}
    assert sess.events == [{"method": "Log.entryAdded"}]
    assert sess.call("Page.enable", a=1) == {"ok": "Page.enable"}
    assert ws.sent[1] == {"id": 2, "method": "Page.enable", "params": {"a": 1}}


def test_call_raises_on_protocol_error() -> None:
    sess = cdp.Session(FakeWs(lambda m, p: {"error": {"message": "nope"}}))
    with pytest.raises(DriveError, match="Bogus.x: nope"):
        sess.call("Bogus.x")


def test_call_wraps_transport_failures_as_browser_errors() -> None:
    class Dead(FakeWs):
        def send(self, raw: str) -> None:
            raise websocket.WebSocketConnectionClosedException("gone")

    with pytest.raises(DriveError) as err:
        cdp.Session(Dead(lambda m, p: {})).call("Page.enable")
    assert err.value.code == EXIT_BROWSER


def test_evaluate_returns_value_or_raises_page_exception() -> None:
    page = FakePage(evals={"1+1": 2, "boom()": ValueError("bad")})
    sess = cdp.Session(page.ws())
    assert sess.evaluate("1+1") == 2
    with pytest.raises(DriveError, match="Error: bad"):
        sess.evaluate("boom()")
    assert (
        page.ws().handler("Runtime.evaluate", {"expression": "1+1"})["result"][
            "result"
        ]["value"]
        == 2
    )


def test_evaluate_exception_without_description_uses_text() -> None:
    ws = FakeWs(
        lambda m, p: {
            "result": {"result": {}, "exceptionDetails": {"text": "Uncaught"}}
        }
    )
    with pytest.raises(DriveError, match="Uncaught"):
        cdp.Session(ws).evaluate("x")


def test_drain_collects_until_timeout_and_restores_timeout() -> None:
    ws = FakeWs(lambda m, p: {"result": {}})
    ws.queue = [{"method": "A"}, {"method": "B"}]
    sess = cdp.Session(ws)
    assert [e["method"] for e in sess.drain(0.1)] == ["A", "B"]
    assert ws.timeout == cdp.CALL_TIMEOUT


def test_close_closes_socket() -> None:
    ws = FakeWs(lambda m, p: {})
    cdp.Session(ws).close()
    assert ws.closed


def test_pick_page_skips_browser_ui_and_needs_a_page() -> None:
    assert cdp.pick_page(PAGE_TARGETS) == "ws://page"
    chrome_only = [
        {"type": "page", "url": "chrome://newtab", "webSocketDebuggerUrl": "ws://n"}
    ]
    assert cdp.pick_page(chrome_only) == "ws://n"
    with pytest.raises(DriveError, match="no page target"):
        cdp.pick_page([PAGE_TARGETS[0]])


def test_probe_returns_none_when_nothing_listens() -> None:
    assert cdp.probe(1, fetch=_fetch(None, [])) is None
    assert cdp.probe(1, fetch=_fetch(HEADLESS, [])) == HEADLESS


def test_connect_refuses_headed_browsers() -> None:
    with pytest.raises(DriveError) as err:
        cdp.connect(9222, fetch=_fetch(HEADED, PAGE_TARGETS), create=lambda u: None)
    assert err.value.code == EXIT_UNSAFE
    assert "Valve Steam" in err.value.message


def test_connect_reports_missing_browser() -> None:
    with pytest.raises(DriveError) as err:
        cdp.connect(9, fetch=_fetch(None, []), create=lambda u: None)
    assert err.value.code == EXIT_BROWSER


def test_connect_opens_the_page_socket() -> None:
    seen: list[str] = []

    def create(url: str) -> FakeWs:
        seen.append(url)
        return FakeWs(lambda m, p: {"result": {}})

    sess = cdp.connect(9341, fetch=_fetch(HEADLESS, PAGE_TARGETS), create=create)
    assert isinstance(sess, cdp.Session)
    assert seen == ["ws://page"]


def test_http_json_reads_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    urls: list[str] = []

    def fake_urlopen(url: str, timeout: float) -> io.BytesIO:
        urls.append(url)
        return io.BytesIO(json.dumps({"ok": True}).encode())

    monkeypatch.setattr(cdp.urllib.request, "urlopen", fake_urlopen)
    assert cdp.http_json(9341, "/json/version") == {"ok": True}
    assert urls == ["http://127.0.0.1:9341/json/version"]


def test_default_create_uses_websocket_client(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(
        cdp.websocket,
        "create_connection",
        lambda url, **kw: calls.append((url, kw)) or "ws",
    )
    assert cdp.create_socket("ws://x") == "ws"
    assert calls == [("ws://x", {"timeout": cdp.CALL_TIMEOUT, "suppress_origin": True})]
