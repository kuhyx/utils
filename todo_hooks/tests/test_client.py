"""Tests for the MCP-over-HTTP client against the stdlib fake server."""

from __future__ import annotations

import socket
from typing import TYPE_CHECKING

import pytest

from todo_hooks.client import (
    DEFAULT_URL,
    McpAuthError,
    McpClient,
    McpError,
    McpToolError,
    McpUnavailable,
    _parse_reply,
    load_token,
)
from todo_hooks.tests._fakes import SESSION, TOKEN, FakeMcp

if TYPE_CHECKING:
    from pathlib import Path


def _client(mcp: FakeMcp, timeout: float = 5.0) -> McpClient:
    return McpClient(mcp.url, TOKEN, timeout=timeout)


def test_load_token_prefers_env(tmp_path: Path) -> None:
    file = tmp_path / "t"
    file.write_text("from-file\n")
    assert load_token({"TODO_MCP_TOKEN": " from-env "}, file) == "from-env"


def test_load_token_falls_back_to_file(tmp_path: Path) -> None:
    file = tmp_path / "t"
    file.write_text("from-file\n")
    assert load_token({}, file) == "from-file"


def test_load_token_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(McpAuthError, match="no token"):
        load_token({}, tmp_path / "absent")


def test_load_token_empty_file_raises(tmp_path: Path) -> None:
    file = tmp_path / "t"
    file.write_text("\n")
    with pytest.raises(McpAuthError):
        load_token({}, file)


def test_from_env_uses_url_override(tmp_path: Path) -> None:
    file = tmp_path / "t"
    file.write_text("tok")
    client = McpClient.from_env({"TODO_MCP_URL": "http://x/mcp"}, file)
    assert client.url == "http://x/mcp"
    assert McpClient.from_env({}, file).url == DEFAULT_URL


def test_handshake_then_call(mcp: FakeMcp) -> None:
    mcp.tools["list_tasks"] = lambda args: f"saw {args['status']}"
    client = _client(mcp)
    assert client.call("list_tasks", {"status": "open"}) == "saw open"
    methods = [r["method"] for r in mcp.requests]
    assert methods == ["initialize", "notifications/initialized", "tools/call"]
    assert mcp.requests[1]["session"] == SESSION
    assert mcp.requests[2]["session"] == SESSION
    assert "text/event-stream" in mcp.requests[0]["accept"]


def test_second_call_reuses_session(mcp: FakeMcp) -> None:
    mcp.tools["get_task"] = lambda args: args["id"]
    client = _client(mcp)
    client.call("get_task", {"id": "a"})
    client.call("get_task", {"id": "b"})
    assert [r["method"] for r in mcp.requests].count("initialize") == 1


def test_json_content_type_is_parsed(mcp: FakeMcp) -> None:
    mcp.mode = "json"
    mcp.tools["get_task"] = lambda _a: "plain"
    assert _client(mcp).call("get_task", {"id": "x"}) == "plain"


def test_no_arguments_sends_empty_object(mcp: FakeMcp) -> None:
    mcp.tools["list_tasks"] = str
    assert _client(mcp).call("list_tasks") == "{}"


def test_bad_token_is_auth_error(mcp: FakeMcp) -> None:
    with pytest.raises(McpAuthError):
        McpClient(mcp.url, "wrong").call("list_tasks")


def test_server_error_is_unavailable(mcp: FakeMcp) -> None:
    mcp.status = 500
    with pytest.raises(McpUnavailable):
        _client(mcp).call("list_tasks")


def test_other_http_status_is_mcp_error(mcp: FakeMcp) -> None:
    mcp.status = 404
    with pytest.raises(McpError) as info:
        _client(mcp).call("list_tasks")
    assert not isinstance(info.value, McpUnavailable)


def test_connection_refused_is_unavailable() -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with pytest.raises(McpUnavailable):
        McpClient(f"http://127.0.0.1:{port}/mcp", "t", timeout=1).call("x")


def test_timeout_is_unavailable(mcp: FakeMcp) -> None:
    mcp.delay = 1.0
    with pytest.raises(McpUnavailable):
        _client(mcp, timeout=0.2).call("list_tasks")


def test_tool_error_flag_raises(mcp: FakeMcp) -> None:
    mcp.mode = "tool-error"
    mcp.tools["close_task"] = lambda _a: "error: evidence: required"
    with pytest.raises(McpToolError, match="evidence"):
        _client(mcp).call("close_task", {"id": "x"})


def test_rpc_error_raises(mcp: FakeMcp) -> None:
    mcp.mode = "rpc-error"
    with pytest.raises(McpError, match="nope"):
        _client(mcp).call("list_tasks")


def test_garbage_body_raises(mcp: FakeMcp) -> None:
    mcp.mode = "garbage"
    with pytest.raises(McpError, match="unparseable"):
        _client(mcp).call("list_tasks")


def test_sse_without_data_raises(mcp: FakeMcp) -> None:
    mcp.mode = "no-data"
    with pytest.raises(McpError, match="unparseable"):
        _client(mcp).call("list_tasks")


def test_stateless_server_needs_no_session(mcp: FakeMcp) -> None:
    mcp.stateless = True
    mcp.tools["x"] = lambda _a: "ok"
    assert _client(mcp).call("x") == "ok"
    assert mcp.requests[-1]["session"] is None


def test_unknown_session_is_mcp_error(mcp: FakeMcp) -> None:
    mcp.tools["x"] = lambda _a: "ok"
    client = _client(mcp)
    client.call("x")
    client._session = "stale"
    with pytest.raises(McpError, match="no session"):
        client.call("x")


def test_close_deletes_session_once(mcp: FakeMcp) -> None:
    mcp.tools["x"] = lambda _a: "ok"
    client = _client(mcp)
    client.close()  # nothing opened: no request
    assert mcp.requests == []
    client.call("x")
    client.close()
    client.close()
    assert [r["method"] for r in mcp.requests].count("DELETE") == 1


def test_close_swallows_errors(mcp: FakeMcp) -> None:
    mcp.tools["x"] = lambda _a: "ok"
    client = _client(mcp)
    client.call("x")
    mcp.stop()
    client.close()  # must not raise


def test_context_manager_closes(mcp: FakeMcp) -> None:
    mcp.tools["x"] = lambda _a: "ok"
    with _client(mcp) as client:
        client.call("x")
    assert mcp.requests[-1]["method"] == "DELETE"


def test_non_object_json_is_unparseable() -> None:
    with pytest.raises(McpError, match="unparseable"):
        _parse_reply("application/json", "[1, 2]")


def test_non_http_url_is_refused() -> None:
    with pytest.raises(McpError, match="unsupported"):
        McpClient("file:///etc/passwd", "t")


def test_exhausted_budget_fails_before_any_request(mcp: FakeMcp) -> None:
    with pytest.raises(McpUnavailable, match="budget"):
        McpClient(mcp.url, TOKEN, budget=0).call("list_tasks")
    assert mcp.requests == []


def test_budget_caps_each_request(mcp: FakeMcp) -> None:
    mcp.delay = 1.0
    with pytest.raises(McpUnavailable):
        McpClient(mcp.url, TOKEN, timeout=5, budget=0.3).call("list_tasks")


def test_from_env_passes_budget(tmp_path: Path) -> None:
    file = tmp_path / "t"
    file.write_text("tok")
    assert McpClient.from_env({}, file, budget=0).call is not None
