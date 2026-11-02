"""The HTTP side of `_fake_rtdb.FakeRtdb`: REST answers and chunked SSE streams."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler
import json
import logging
from typing import TYPE_CHECKING, ClassVar
from urllib.parse import parse_qs, unquote, urlsplit

if TYPE_CHECKING:
    from leetcode_coach.tests._fake_rtdb import FakeRtdb

_LOG = logging.getLogger(__name__)


def segments(path: str) -> list[str]:
    """``a/b%2Fc/`` -> ``["a", "b/c"]``."""
    return [unquote(p) for p in path.strip("/").split("/") if p]


class _Handler(BaseHTTPRequestHandler):
    """REST and SSE answers from `fake` (set by `handler_for`)."""

    fake: ClassVar[FakeRtdb]
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, /, *args: object) -> None:
        del fmt, args

    def _reply(self, status: int, body: object = None) -> None:
        raw = b"" if status == 204 else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _handle(self, method: str) -> None:
        split = urlsplit(self.path)
        query = parse_qs(split.query)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        self.fake.requests.append((method, split.path, split.query))
        token = query.get("auth", [""])[0]
        if not token:
            self._reply(401, {"error": "Permission denied"})
            return
        self.fake.tokens.append(token)
        if (status := self.fake.take_failure()) is not None:
            self._reply(status, {"error": "injected"})
            return
        segs = segments(split.path.removesuffix(".json"))
        if method == "GET" and "event-stream" in self.headers.get("Accept", ""):
            self._stream(segs)
            return
        if method == "GET":
            self._reply(200, self.fake.node(segs))
            return
        stored = self.fake.apply(method, segs, json.loads(raw) if raw else None)
        silent = query.get("print", [""])[0] == "silent"
        self._reply(204 if silent or method == "DELETE" else 200, stored)

    def _chunk(self, text: str) -> None:
        data = text.encode()
        self.wfile.write(f"{len(data):x}\r\n".encode() + data + b"\r\n")
        self.wfile.flush()

    def _stream(self, segs: list[str]) -> None:
        self.close_connection = True
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        stream = self.fake.open_stream(segs)
        try:
            while (item := stream.items.get()) is not None:
                self._chunk(f"event: {item[0]}\ndata: {item[1]}\n\n")
            self.wfile.write(b"0\r\n\r\n")
        except OSError as exc:
            _LOG.warning("fake RTDB stream: the client hung up (%s)", exc)
        finally:
            self.fake.close_stream(stream)

    def do_GET(self) -> None:
        self._handle("GET")

    def do_PUT(self) -> None:
        self._handle("PUT")

    def do_PATCH(self) -> None:
        self._handle("PATCH")

    def do_DELETE(self) -> None:
        self._handle("DELETE")


def handler_for(fake: FakeRtdb) -> type[BaseHTTPRequestHandler]:
    """A request handler class bound to `fake`."""
    return type("Handler", (_Handler,), {"fake": fake})
