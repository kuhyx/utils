"""Test doubles: a scriptable task client and a stdlib fake MCP HTTP server."""

from __future__ import annotations

from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time
from typing import TYPE_CHECKING, Any

from todo_hooks.client import McpToolError

if TYPE_CHECKING:
    from collections.abc import Callable

TOKEN = "test-token"
SESSION = "sess-1"


def detail(
    task_id: str,
    *,
    repo: str = "kuhyx/demo",
    done_check: str | None = "true",
    text: str = "# Title\n\nBody",
    status: str = "todo",
    by: str = "claude",
) -> str:
    """Build a get_task reply the way the Dart server formats it."""
    lines = [f"id: {task_id}", "priority: medium", f"status: {status}"]
    lines += ["created: 2026-11-02T10:00:00", "updated: 2026-11-02T10:00:00"]
    lines.append(f"repo: {repo}")
    if done_check is not None:
        lines.append(f"done_check: {done_check}")
    lines += [f"by: {by}", "---", text]
    return "\n".join(lines)


def line(task_id: str, repo: str = "kuhyx/demo", title: str = "# Title") -> str:
    """One list_tasks line: id8, status, priority, repo, title."""
    return "\t".join([task_id[:8], "todo", "medium", repo, title])


@dataclass
class FakeClient:
    """Answers tool calls from a dict of tool -> reply (str, callable, or error)."""

    replies: dict[str, Any] = field(default_factory=dict)
    calls: list[tuple[str, dict[str, str]]] = field(default_factory=list)

    def call(self, tool: str, arguments: dict[str, str] | None = None) -> str:
        """Record the call and return or raise the scripted reply."""
        args = arguments or {}
        self.calls.append((tool, args))
        reply = self.replies.get(tool, "")
        if callable(reply):
            reply = reply(args)
        if isinstance(reply, Exception):
            raise reply
        return str(reply)

    def close(self) -> None:
        """Match the real client; nothing to release."""

    def tools(self) -> list[str]:
        """Names of the tools called, in order."""
        return [name for name, _ in self.calls]


def task_client(*details: str, **extra: Any) -> FakeClient:  # noqa: ANN401
    """A client whose get_task answers by id prefix from `details`."""
    by_id = {d.splitlines()[0].removeprefix("id: "): d for d in details}

    def get_task(args: dict[str, str]) -> str | Exception:
        for task_id, text in by_id.items():
            if task_id.startswith(args["id"]):
                return text
        return McpToolError("error: id: no live note")

    return FakeClient({"get_task": get_task, "close_task": "closed x", **extra})


class FakeMcp:
    """A loopback server speaking just enough Streamable HTTP like mcp_dart."""

    def __init__(self) -> None:
        self.tools: dict[str, Callable[[dict[str, Any]], str]] = {}
        self.requests: list[dict[str, Any]] = []
        self.mode = "sse"  # sse | json | garbage | rpc-error | tool-error
        self.status = 200
        self.delay = 0.0
        self.stateless = False
        self.token = TOKEN
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: object) -> None:
                return

            def _send(
                self,
                code: int,
                body: str,
                ctype: str,
                extra: dict[str, str] | None = None,
            ) -> None:
                data = body.encode()
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                for key, value in (extra or {}).items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(data)

            def do_DELETE(self) -> None:
                owner.requests.append(
                    {"method": "DELETE", "session": self.headers.get("Mcp-Session-Id")}
                )
                self._send(200, "", "text/plain")

            def do_POST(self) -> None:
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                owner.requests.append(
                    {
                        "method": body.get("method"),
                        "body": body,
                        "session": self.headers.get("Mcp-Session-Id"),
                        "accept": self.headers.get("Accept"),
                    }
                )
                if self.headers.get("Authorization") != f"Bearer {owner.token}":
                    self._send(403, "Forbidden", "text/plain")
                    return
                if owner.delay:
                    time.sleep(owner.delay)
                if owner.status != 200:
                    self._send(owner.status, "boom", "text/plain")
                    return
                self._answer(body)

            def _answer(self, body: dict[str, Any]) -> None:
                method = body.get("method")
                if method == "notifications/initialized":
                    self._send(202, "", "text/plain")
                elif method == "initialize":
                    result = {"result": {"protocolVersion": "2025-03-26"}}
                    self._reply(
                        body,
                        result,
                        {} if owner.stateless else {"Mcp-Session-Id": SESSION},
                    )
                elif (
                    not owner.stateless
                    and self.headers.get("Mcp-Session-Id") != SESSION
                ):
                    err = {"error": {"code": -32000, "message": "no session"}}
                    self._reply(body, err)
                else:
                    self._tool(body)

            def _tool(self, body: dict[str, Any]) -> None:
                params = body["params"]
                if owner.mode == "rpc-error":
                    self._reply(body, {"error": {"code": -32601, "message": "nope"}})
                elif owner.mode == "garbage":
                    self._send(200, "not json at all", "application/json")
                elif owner.mode == "no-data":
                    self._send(200, "event: ping\n\n", "text/event-stream")
                else:
                    text = owner.tools[params["name"]](params["arguments"])
                    result = {
                        "content": [{"type": "text", "text": text}],
                        "isError": owner.mode == "tool-error",
                    }
                    self._reply(body, {"result": result})

            def _reply(
                self,
                body: dict[str, Any],
                part: dict[str, Any],
                extra: dict[str, str] | None = None,
            ) -> None:
                payload = json.dumps({"jsonrpc": "2.0", "id": body.get("id"), **part})
                if owner.mode == "json":
                    self._send(200, payload, "application/json", extra)
                else:
                    sse = f"event: message\ndata: {payload}\n\n"
                    self._send(200, sse, "text/event-stream", extra)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        """The /mcp endpoint on the ephemeral port."""
        return f"http://127.0.0.1:{self._server.server_address[1]}/mcp"

    def start(self) -> FakeMcp:
        """Begin serving in a daemon thread."""
        self._thread.start()
        return self

    def stop(self) -> None:
        """Stop serving and release the port."""
        self._server.shutdown()
        self._server.server_close()


BODY = """Intro text.

## Todo:
- Add retry to sync | done_check: pytest -q tests/test_retry.py
- Document the flag
* Star bullet | done_check: true

## Other
- not a todo | done_check: false
"""


class FakeGh:
    """Scripted `gh api` answers by commit sha."""

    def __init__(self, pulls: dict[str, list[dict[str, object]]]) -> None:
        self.pulls = pulls
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str]) -> str:
        self.calls.append(args)
        sha = args[1].split("/")[4]
        return json.dumps(self.pulls.get(sha, []))


def make_pr(
    number: int, body: str | None = BODY, merged: str | None = "2026-11-01"
) -> dict[str, object]:
    return {"number": number, "body": body, "merged_at": merged}
