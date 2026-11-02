"""MCP-over-HTTP JSON-RPC client for the todo server (stdlib only)."""

from __future__ import annotations

import contextlib
import http.client
import json
import time
from typing import TYPE_CHECKING, Any, Protocol, Self
import urllib.error
import urllib.request

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

DEFAULT_URL = "http://127.0.0.1:8735/mcp"
DEFAULT_TIMEOUT = 5.0
_PROTOCOL = "2025-03-26"
_HTTP_AUTH = (401, 403)
_HTTP_SERVER_ERROR = 500


class McpError(Exception):
    """Any failure talking to the todo MCP server."""


class McpUnavailable(McpError):
    """Server down, timed out, or answering 5xx."""


class McpAuthError(McpError):
    """No token, or the server rejected it."""


class McpToolError(McpError):
    """The tool ran but reported an error."""


class TaskClient(Protocol):
    """What the hooks need from a client; tests substitute a fake."""

    def call(self, tool: str, arguments: dict[str, str] | None = None) -> str:
        """Call a tool and return its text."""
        ...

    def close(self) -> None:
        """Release the server session."""
        ...


def load_token(env: Mapping[str, str], token_file: Path) -> str:
    """Return ``TODO_MCP_TOKEN`` from env, else the token file's content."""
    token = env.get("TODO_MCP_TOKEN", "").strip()
    if not token:
        try:
            token = token_file.read_text(encoding="utf-8").strip()
        except OSError:
            token = ""
    if not token:
        msg = f"no token: set TODO_MCP_TOKEN or create {token_file}"
        raise McpAuthError(msg)
    return token


def _parse_reply(content_type: str, body: str) -> dict[str, Any]:
    candidates = [body]
    if "text/event-stream" in content_type:
        candidates = [
            row.removeprefix("data:").strip()
            for row in body.splitlines()
            if row.startswith("data:")
        ]
    for raw in candidates:
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(message, dict):
            return message
    msg = f"unparseable response: {body[:80]!r}"
    raise McpError(msg)


class McpClient:
    """One lazily initialised MCP session; ``close`` it (or use ``with``)."""

    def __init__(
        self,
        url: str,
        token: str,
        timeout: float = DEFAULT_TIMEOUT,
        budget: float | None = None,
    ) -> None:
        if not url.startswith(("http://", "https://")):
            msg = f"unsupported MCP url: {url}"
            raise McpError(msg)
        self.url = url
        self._token = token
        self._timeout = timeout
        self._deadline = None if budget is None else time.monotonic() + budget
        self._session: str | None = None
        self._ready = False
        self._next_id = 0

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str],
        token_file: Path,
        timeout: float = DEFAULT_TIMEOUT,
        budget: float | None = None,
    ) -> McpClient:
        """Build from ``TODO_MCP_URL`` and the token (env or file)."""
        url = env.get("TODO_MCP_URL") or DEFAULT_URL
        return cls(url, load_token(env, token_file), timeout, budget)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _send(
        self, payload: dict[str, Any] | None, method: str = "POST"
    ) -> tuple[str, str, Mapping[str, str]]:
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._session:
            headers["Mcp-Session-Id"] = self._session
        timeout = self._timeout
        if self._deadline is not None:
            timeout = min(timeout, self._deadline - time.monotonic())
            if timeout <= 0:
                msg = "time budget exhausted"
                raise McpUnavailable(msg)
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            self.url, data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as reply:
                body = reply.read().decode("utf-8", "replace")
                return reply.headers.get("Content-Type", ""), body, reply.headers
        except urllib.error.HTTPError as err:
            err.close()
            if err.code in _HTTP_AUTH:
                msg = f"server rejected the token (HTTP {err.code})"
                raise McpAuthError(msg) from err
            msg = f"HTTP {err.code}"
            if err.code >= _HTTP_SERVER_ERROR:
                raise McpUnavailable(msg) from err
            raise McpError(msg) from err
        except (urllib.error.URLError, OSError, http.client.HTTPException) as err:
            msg = f"cannot reach {self.url}: {getattr(err, 'reason', err)}"
            raise McpUnavailable(msg) from err

    def _rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._next_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": method,
            "params": params,
        }
        ctype, body, headers = self._send(payload)
        if method == "initialize":
            self._session = headers.get("Mcp-Session-Id")
        message = _parse_reply(ctype, body)
        if "error" in message:
            raise McpError(str(message["error"].get("message", message["error"])))
        return message.get("result", {})

    def _handshake(self) -> None:
        info = {"name": "todo-hooks", "version": "1"}
        self._rpc(
            "initialize",
            {"protocolVersion": _PROTOCOL, "capabilities": {}, "clientInfo": info},
        )
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self._ready = True

    def call(self, tool: str, arguments: dict[str, str] | None = None) -> str:
        """Call `tool` and return its text; ``McpToolError`` if it reports one."""
        if not self._ready:
            self._handshake()
        result = self._rpc("tools/call", {"name": tool, "arguments": arguments or {}})
        text = "\n".join(
            part.get("text", "")
            for part in result.get("content", [])
            if part.get("type") == "text"
        )
        if result.get("isError"):
            raise McpToolError(text)
        return text

    def close(self) -> None:
        """End the server session (best effort, never raises)."""
        if self._session is None:
            return
        with contextlib.suppress(McpError):
            self._send(None, method="DELETE")
        self._session = None
        self._ready = False
