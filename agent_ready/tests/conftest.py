"""Fixtures: generated site trees and loopback HTTP servers that serve them."""

from __future__ import annotations

import socket
import threading
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from agent_ready.tests import sitegen

_MIME = {
    ".html": "text/html; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".xml": "application/xml",
    ".json": "application/json",
}


def _resolve(root: Path, path: str) -> Path | None:
    """Map a URL path to a file the way a static host does."""
    rel = path.split("?", 1)[0].lstrip("/")
    cand = root / rel
    if path.endswith("/"):
        cand = cand / "index.html"
    return cand if cand.is_file() else None


def make_handler(root: Path, mode: str, block_ua: str) -> type[BaseHTTPRequestHandler]:
    """Build a handler class.

    ``mode`` is ``good`` (real 404s), ``spa`` (200 index.html for every path,
    the kuhy.duckdns.org trap) or ``json404`` (every non-root path is a JSON
    404, the popes.kuhy.duckdns.org shape).
    """

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:  # silence test output
            return

        def _send(
            self,
            status: int,
            ctype: str,
            body: bytes,
            extra: dict[str, str] | None = None,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if block_ua and block_ua in self.headers.get("User-Agent", ""):
                self._send(403, "text/html", b"<html>Just a moment...</html>")
                return
            origin = f"http://{self.headers['Host']}"
            if mode == "spa" or (mode == "json404" and self.path == "/"):
                body = (root / "index.html").read_bytes()
                self._send(200, "text/html; charset=utf-8", body)
                return
            target = None if mode == "json404" else _resolve(root, self.path)
            if target is None:
                if mode == "json404":
                    self._send(404, "application/json", b'{"detail":"Not Found"}')
                else:
                    self._send(404, "text/html", (root / "404.html").read_bytes())
                return
            if target.name == "ai-catalog.json":
                ctype = "application/ai-catalog+json"
            else:
                ctype = _MIME.get(target.suffix, "application/octet-stream")
            body = target.read_bytes().replace(sitegen.ORIGIN.encode(), origin.encode())
            extra = {}
            if self.path == "/":
                extra["Link"] = '</.well-known/ai-catalog.json>; rel="ai-catalog"'
            self._send(200, ctype, body, extra)

        def do_POST(self) -> None:
            """Minimal MCP: answer initialize at /mcp in good mode only."""
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            if mode == "good" and self.path == "/mcp":
                self._send(
                    200, "application/json", b'{"jsonrpc":"2.0","id":1,"result":{}}'
                )
            else:
                self._send(200, "text/html", (root / "index.html").read_bytes())

    return Handler


@pytest.fixture
def good_dir(tmp_path: Path) -> Path:
    """A compliant build output."""
    return sitegen.build_good(tmp_path / "good")


@pytest.fixture
def bad_dir(tmp_path: Path) -> Path:
    """A build output failing every find/read item."""
    return sitegen.build_bad(tmp_path / "bad")


@pytest.fixture
def serve() -> Iterator[Callable[..., str]]:
    """Start loopback servers on demand; return their base URL."""
    servers: list[ThreadingHTTPServer] = []

    def start(root: Path, mode: str = "good", block_ua: str = "") -> str:
        server = ThreadingHTTPServer(
            ("127.0.0.1", 0), make_handler(root, mode, block_ua)
        )
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return f"http://127.0.0.1:{server.server_address[1]}"

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


@pytest.fixture
def dead_url() -> str:
    """A loopback URL with nothing listening (connection refused)."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return f"http://127.0.0.1:{port}"
