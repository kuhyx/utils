# Copyright (c) 2026 Krzysztof Rudnicki
"""The MCP client against a real local HTTP server (never the live todo app)."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import threading
from typing import TYPE_CHECKING, ClassVar

import pytest

from feedback_inbox._todo import McpTodoClient, TodoError

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

FULL_ID = "a1b2c3d4" + "e" * 28


class _Handler(BaseHTTPRequestHandler):
    seen: ClassVar[list[dict[str, object]]] = []
    headers_seen: ClassVar[list[dict[str, str]]] = []
    tool_text: ClassVar[str] = f"added {FULL_ID}\nline"
    is_error: ClassVar[bool] = False
    status: ClassVar[int] = 200
    sse: ClassVar[bool] = True

    def do_POST(self) -> None:
        length = int(self.headers["Content-Length"])
        body = json.loads(self.rfile.read(length))
        type(self).seen.append(body)
        type(self).headers_seen.append({k.lower(): v for k, v in self.headers.items()})
        if type(self).status != 200:
            self.send_response(type(self).status)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("mcp-session-id", "sess-1")
        self.end_headers()
        method = body.get("method")
        if method == "initialize":
            self.wfile.write(
                b'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{}}\n\n'
            )
        elif method == "tools/call":
            result: dict[str, object] = {
                "content": [{"type": "text", "text": type(self).tool_text}],
            }
            if type(self).is_error:
                result["isError"] = True
            reply = json.dumps({"jsonrpc": "2.0", "id": 2, "result": result})
            out = f"event: message\ndata: {reply}\n\n" if type(self).sse else reply
            self.wfile.write(out.encode())

    def log_message(self, *_args: object) -> None:
        return


@pytest.fixture
def server() -> Iterator[str]:
    _Handler.seen = []
    _Handler.headers_seen = []
    _Handler.tool_text = f"added {FULL_ID}\nline"
    _Handler.is_error = False
    _Handler.status = 200
    _Handler.sse = True
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}/mcp"
    httpd.shutdown()
    httpd.server_close()
    thread.join()


def _client(url: str, tmp_path: Path) -> McpTodoClient:
    token = tmp_path / "token"
    token.write_text("secret-token\n", encoding="utf-8")
    return McpTodoClient(url, token)


def test_add_task_round_trip(server: str, tmp_path: Path) -> None:
    ref = _client(server, tmp_path).add_task("kuhyx/cleanup-plate", "t", "b")
    assert (ref.task_id, ref.merged) == (FULL_ID, False)
    methods = [m.get("method") for m in _Handler.seen]
    assert methods == ["initialize", "notifications/initialized", "tools/call"]
    call = _Handler.seen[2]["params"]
    assert call == {
        "name": "add_task",
        "arguments": {
            "repo": "kuhyx/cleanup-plate",
            "title": "t",
            "body": "b",
            "new_note": True,
        },
    }
    assert _Handler.headers_seen[0]["authorization"] == "Bearer secret-token"
    assert _Handler.headers_seen[2]["mcp-session-id"] == "sess-1"


def test_plain_json_reply_and_merge(server: str, tmp_path: Path) -> None:
    _Handler.sse = False
    _Handler.tool_text = f"merged into {FULL_ID}\nstart: skipped"
    ref = _client(server, tmp_path).add_task("r/x", "t", "b")
    assert (ref.task_id, ref.merged) == (FULL_ID, True)


def test_tool_error_is_reported(server: str, tmp_path: Path) -> None:
    _Handler.is_error = True
    _Handler.tool_text = "boom"
    with pytest.raises(TodoError, match="boom"):
        _client(server, tmp_path).add_task("r/x", "t", "b")


def test_unexpected_reply_text(server: str, tmp_path: Path) -> None:
    _Handler.tool_text = "who knows"
    with pytest.raises(TodoError, match="who knows"):
        _client(server, tmp_path).add_task("r/x", "t", "b")


def test_http_error(server: str, tmp_path: Path) -> None:
    _Handler.status = 403
    with pytest.raises(TodoError, match="403"):
        _client(server, tmp_path).add_task("r/x", "t", "b")


def test_unreachable_server(tmp_path: Path) -> None:
    with pytest.raises(TodoError, match="unreachable"):
        _client("http://127.0.0.1:9/mcp", tmp_path).add_task("r/x", "t", "b")


def test_missing_token(tmp_path: Path) -> None:
    client = McpTodoClient("http://127.0.0.1:9/mcp", tmp_path / "none")
    with pytest.raises(TodoError, match="token"):
        client.add_task("r/x", "t", "b")


def test_missing_session_header(server: str, tmp_path: Path) -> None:
    class _NoSession(_Handler):
        def do_POST(self) -> None:
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

    httpd = HTTPServer(("127.0.0.1", 0), _NoSession)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        client = _client(f"http://127.0.0.1:{httpd.server_port}/mcp", tmp_path)
        with pytest.raises(TodoError, match="session"):
            client.add_task("r/x", "t", "b")
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join()


def test_garbage_json(server: str, tmp_path: Path) -> None:
    _Handler.sse = False
    _Handler.tool_text = "x"

    class _Bad(_Handler):
        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(200)
            self.send_header("mcp-session-id", "s")
            self.end_headers()
            if body.get("method") == "tools/call":
                self.wfile.write(b"not json")

    httpd = HTTPServer(("127.0.0.1", 0), _Bad)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        client = _client(f"http://127.0.0.1:{httpd.server_port}/mcp", tmp_path)
        with pytest.raises(TodoError, match="unparsable"):
            client.add_task("r/x", "t", "b")
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join()


def test_update_task_replaces_title_and_body(server: str, tmp_path: Path) -> None:
    _Handler.tool_text = f"updated {FULL_ID}\nline"
    _client(server, tmp_path).update_task(FULL_ID, "MANUAL WORK REQUIRED: x", "b")
    call = _Handler.seen[2]["params"]
    assert call == {
        "name": "update_task",
        "arguments": {"id": FULL_ID, "title": "MANUAL WORK REQUIRED: x", "body": "b"},
    }


def test_update_task_refused(server: str, tmp_path: Path) -> None:
    _Handler.tool_text = "no such task"
    with pytest.raises(TodoError, match="no such task"):
        _client(server, tmp_path).update_task(FULL_ID, "t", "b")
