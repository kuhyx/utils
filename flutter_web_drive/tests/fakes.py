"""In-memory stand-ins for a headless chromium page and its CDP websocket."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import websocket

from flutter_web_drive import semantics

Handler = Callable[[str, dict[str, Any]], dict[str, Any]]


def node(
    nid: int,
    label: str = "",
    *,
    role: str = "button",
    value: str = "",
    rect: tuple[int, int, int, int] = (0, 0, 80, 40),
    tappable: bool = True,
    flags: tuple[str, ...] = (),
    tag: str = "flt-semantics",
) -> dict[str, Any]:
    """Build one raw node record the way COLLECT_JS returns it."""
    x, y, w, h = rect
    return {
        "id": nid,
        "tag": tag,
        "role": role,
        "label": label,
        "value": value,
        "x": x,
        "y": y,
        "w": w,
        "h": h,
        "tappable": tappable,
        "flags": list(flags),
    }


class FakeWs:
    """A websocket whose replies come from a handler, with queued events."""

    def __init__(
        self, handler: Handler, events: list[dict[str, Any]] | None = None
    ) -> None:
        """Answer each request with ``handler``; replay ``events`` on enable."""
        self.handler = handler
        self.events = list(events or [])
        self.sent: list[dict[str, Any]] = []
        self.queue: list[dict[str, Any]] = []
        self.timeout: float | None = None
        self.closed = False

    def send(self, raw: str) -> None:
        """Record the request and queue its reply (events first on enable)."""
        msg = json.loads(raw)
        self.sent.append(msg)
        if msg["method"] in {"Runtime.enable", "Log.enable"}:
            self.queue.extend(self.events)
            self.events = []
        self.queue.append(
            {"id": msg["id"], **self.handler(msg["method"], msg["params"])}
        )

    def recv(self) -> str:
        """Pop the next queued message, or time out like the real client."""
        if not self.queue:
            raise websocket.WebSocketTimeoutException("timed out")
        return json.dumps(self.queue.pop(0))

    def settimeout(self, seconds: float) -> None:
        """Remember the timeout so tests can assert drain restored it."""
        self.timeout = seconds

    def close(self) -> None:
        """Mark closed."""
        self.closed = True


@dataclass
class FakePage:
    """A Flutter web page as seen through Runtime.evaluate and Input.*."""

    nodes: list[dict[str, Any]] = field(default_factory=list)
    semantics_on: bool = True
    flutter_ready: bool = True
    focused: bool = True
    href: str = "http://127.0.0.1:1/"
    viewport: tuple[int, int] = (1400, 900)
    stats: dict[str, Any] = field(
        default_factory=lambda: {"w": 1400, "h": 900, "colours": 180, "stddev": 9.0},
    )
    evals: dict[str, Any] = field(default_factory=dict)
    clicks: list[tuple[float, float]] = field(default_factory=list)

    def evaluate(self, expr: str) -> dict[str, Any]:
        """Answer the driver's known JS snippets; fall back to ``evals``."""
        value: Any
        if expr == semantics.ENABLE_JS:
            value = "on" if self.semantics_on else "missing"
        elif expr == semantics.COLLECT_JS:
            value = self.nodes if self.semantics_on else []
        elif expr == semantics.FLUTTER_READY_JS:
            value = self.flutter_ready
        elif expr == semantics.FOCUS_JS:
            value = self.focused
        elif expr == semantics.VIEWPORT_JS:
            value = list(self.viewport)
        elif expr == "location.href":
            value = self.href
        elif expr.startswith(semantics.IMAGE_STATS_FN):
            value = self.stats
        elif expr in self.evals:
            value = self.evals[expr]
            if isinstance(value, Exception):
                return {
                    "result": {
                        "result": {"type": "object"},
                        "exceptionDetails": {
                            "text": "Uncaught",
                            "exception": {"description": f"Error: {value}\n    at x"},
                        },
                    }
                }
        else:  # pragma: no cover - a test sent JS the fake does not model
            raise AssertionError(f"unexpected evaluate: {expr[:80]}")
        return {"result": {"result": {"type": "object", "value": value}}}

    def handle(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """CDP handler for FakeWs."""
        if method == "Runtime.evaluate":
            return self.evaluate(params["expression"])
        if method == "Page.captureScreenshot":
            return {"result": {"data": "iVBORw0KGgo="}}
        if method == "Input.dispatchMouseEvent" and params["type"] == "mouseReleased":
            self.clicks.append((params["x"], params["y"]))
        return {"result": {}}

    def ws(self, events: list[dict[str, Any]] | None = None) -> FakeWs:
        """A fresh websocket onto this page."""
        return FakeWs(self.handle, events)


class FakeClock:
    """Deterministic monotonic clock; sleeping advances it."""

    def __init__(self) -> None:
        """Start at t=0."""
        self.t = 0.0
        self.slept: list[float] = []

    def now(self) -> float:
        """Current fake time."""
        return self.t

    def sleep(self, seconds: float) -> None:
        """Advance fake time."""
        self.slept.append(seconds)
        self.t += seconds


HEADLESS = {
    "Browser": "Chrome/155",
    "User-Agent": "Mozilla/5.0 HeadlessChrome/155.0.0.0",
}
HEADED = {"Browser": "Chrome/126", "User-Agent": "Mozilla/5.0 Valve Steam Client"}
PAGE_TARGETS = [
    {
        "type": "browser_ui",
        "url": "chrome://omnibox",
        "webSocketDebuggerUrl": "ws://ui",
    },
    {"type": "page", "url": "http://127.0.0.1:1/", "webSocketDebuggerUrl": "ws://page"},
]
