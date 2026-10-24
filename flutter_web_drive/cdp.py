"""Minimal CDP client: find the headless page, call methods, collect events."""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Callable
from typing import Any, Protocol

import websocket

from flutter_web_drive.errors import EXIT_BROWSER, EXIT_UNSAFE, DriveError

CALL_TIMEOUT = 30.0

Fetch = Callable[[int, str], Any]


class Socket(Protocol):
    """The slice of websocket-client's WebSocket the session uses."""

    def send(self, payload: str) -> Any: ...
    def recv(self) -> Any: ...
    def settimeout(self, timeout: float) -> None: ...
    def close(self) -> None: ...


def http_json(port: int, path: str) -> Any:
    """GET a DevTools HTTP endpoint on loopback and decode the JSON."""
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=2.0) as resp:
        return json.load(resp)


def create_socket(url: str) -> Socket:
    """Open the page websocket (origin suppressed: chromium rejects foreign ones)."""
    return websocket.create_connection(url, timeout=CALL_TIMEOUT, suppress_origin=True)


class Session:
    """One request/response CDP conversation over a page websocket."""

    def __init__(self, ws: Socket) -> None:
        """Wrap an open websocket."""
        self.ws = ws
        self.next_id = 0
        self.events: list[dict[str, Any]] = []

    def call(self, method: str, **params: Any) -> dict[str, Any]:
        """Send one command and return its result; stash events seen meanwhile."""
        self.next_id += 1
        msg_id = self.next_id
        try:
            self.ws.send(json.dumps({"id": msg_id, "method": method, "params": params}))
            while True:
                msg = json.loads(self.ws.recv())
                if msg.get("id") == msg_id:
                    break
                self.events.append(msg)
        except (OSError, websocket.WebSocketException) as exc:
            raise DriveError(
                "cdp", f"{method}: connection lost ({exc})", EXIT_BROWSER
            ) from exc
        if "error" in msg:
            raise DriveError(
                "cdp", f"{method}: {msg['error'].get('message', msg['error'])}"
            )
        return msg.get("result", {})

    def evaluate(self, expr: str) -> Any:
        """Evaluate JS in the page (promises awaited); page exceptions raise."""
        res = self.call(
            "Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True
        )
        if "exceptionDetails" in res:
            det = res["exceptionDetails"]
            desc = det.get("exception", {}).get("description") or det.get(
                "text", "exception"
            )
            raise DriveError("eval", desc.splitlines()[0])
        return res.get("result", {}).get("value")

    def drain(self, seconds: float) -> list[dict[str, Any]]:
        """Collect queued events until ``seconds`` pass with none; return all seen."""
        self.ws.settimeout(seconds)
        try:
            while True:
                self.events.append(json.loads(self.ws.recv()))
        except (OSError, websocket.WebSocketException):
            pass  # the timeout is how a drain ends
        self.ws.settimeout(CALL_TIMEOUT)
        return self.events

    def close(self) -> None:
        """Detach; the browser and page keep running."""
        self.ws.close()


def pick_page(targets: list[dict[str, Any]]) -> str:
    """Websocket URL of the app page: a ``page`` target, preferring non-chrome:// ones."""
    pages = [t for t in targets if t.get("type") == "page"]
    if not pages:
        raise DriveError("connect", "no page target in the browser", EXIT_BROWSER)
    pages.sort(key=lambda t: str(t.get("url", "")).startswith("chrome"))
    return str(pages[0]["webSocketDebuggerUrl"])


def probe(port: int, *, fetch: Fetch = http_json) -> dict[str, Any] | None:
    """``/json/version`` of whatever listens on ``port``, or None if nothing does."""
    try:
        return dict(fetch(port, "/json/version"))
    except OSError:
        return None


def is_headless(version: dict[str, Any]) -> bool:
    """True only for a headless chromium: the one browser we may send input to."""
    return "HeadlessChrome" in str(version.get("User-Agent", ""))


def connect(
    port: int,
    *,
    fetch: Fetch = http_json,
    create: Callable[[str], Socket] = create_socket,
) -> Session:
    """Attach to the headless browser on ``port``; refuse anything with a window."""
    version = probe(port, fetch=fetch)
    if version is None:
        raise DriveError(
            "connect", f"no browser on CDP port {port}; run start first", EXIT_BROWSER
        )
    if not is_headless(version):
        agent = version.get("User-Agent", "?")
        raise DriveError(
            "connect",
            f"CDP port {port} is not headless ({agent}); refusing to drive it",
            EXIT_UNSAFE,
        )
    return Session(create(pick_page(fetch(port, "/json"))))
