# Copyright (c) 2026 Krzysztof Rudnicki
"""The todo app's MCP server as a minimal ``add_task`` client."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import TYPE_CHECKING, Protocol
import urllib.error
import urllib.request

if TYPE_CHECKING:
    from pathlib import Path

_PROTOCOL = "2025-03-26"
_TIMEOUT = 20
_REPLY = re.compile(r"^(added|merged into|appended to) (\S+)")


class TodoError(Exception):
    """The todo server could not take the task."""


@dataclass(frozen=True)
class TaskRef:
    """The task a call created (or the note it was merged into)."""

    task_id: str
    merged: bool


class TodoClient(Protocol):
    """What the inbox needs from a todo app."""

    def add_task(self, repo: str, title: str, body: str) -> TaskRef:
        """Create one task in its own note and return its id."""
        raise NotImplementedError

    def update_task(self, task_id: str, title: str, body: str) -> None:
        """Replace the task's stored title and body with exactly these."""
        raise NotImplementedError


class McpTodoClient:
    """Streamable-HTTP MCP client: initialize, then one ``add_task`` call."""

    def __init__(self, url: str, token_file: Path) -> None:
        """Remember where the server and the (lazily read) token are."""
        self._url = url
        self._token_file = token_file

    def add_task(self, repo: str, title: str, body: str) -> TaskRef:
        """Create a task with its own note via ``add_task``.

        The server stores a ``new_note`` title as ``<name> todos: <title>``;
        :meth:`update_task` restores the exact title (and drops the
        ``## <title>`` section the server adds) afterwards.
        """
        arguments = {"repo": repo, "title": title, "body": body, "new_note": True}
        said = self._call("add_task", arguments)
        found = _REPLY.match(said)
        if not found:
            msg = f"add_task refused: {said[:120]}"
            raise TodoError(msg)
        return TaskRef(task_id=found.group(2), merged=found.group(1) != "added")

    def update_task(self, task_id: str, title: str, body: str) -> None:
        """Rewrite via ``update_task``: exact title, and body with no sections."""
        said = self._call("update_task", {"id": task_id, "title": title, "body": body})
        if not said.startswith("updated"):
            msg = f"update_task refused: {said[:120]}"
            raise TodoError(msg)

    def _call(self, tool: str, arguments: dict[str, object]) -> str:
        token = self._token()
        session = self._initialize(token)
        payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments},
        }
        return _tool_text(self._post(token, payload, session)[1])

    def _token(self) -> str:
        try:
            return self._token_file.read_text(encoding="utf-8").strip()
        except OSError as exc:
            msg = f"token file unreadable: {self._token_file}"
            raise TodoError(msg) from exc

    def _initialize(self, token: str) -> str:
        init = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": _PROTOCOL,
                "capabilities": {},
                "clientInfo": {"name": "feedback-inbox", "version": "0.1.0"},
            },
        }
        headers, _body = self._post(token, init, None)
        session = headers.get("mcp-session-id")
        if not session:
            msg = "todo server sent no session id"
            raise TodoError(msg)
        self._post(
            token,
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            session,
        )
        return session

    def _post(
        self,
        token: str,
        payload: dict[str, object],
        session: str | None,
    ) -> tuple[dict[str, str], str]:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if session:
            headers["mcp-session-id"] = session
        request = urllib.request.Request(
            self._url,
            data=json.dumps(payload).encode(),
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT) as resp:
                return (
                    {k.lower(): v for k, v in resp.headers.items()},
                    resp.read().decode(),
                )
        except urllib.error.HTTPError as exc:
            exc.close()
            msg = f"todo server answered HTTP {exc.code}"
            raise TodoError(msg) from exc
        except OSError as exc:
            msg = f"todo server unreachable: {exc}"
            raise TodoError(msg) from exc


def _tool_text(body: str) -> str:
    """The text a tool call answered; an MCP-level error becomes TodoError."""
    text = body.strip()
    if not text.startswith("{"):
        lines = [x[5:].strip() for x in text.splitlines() if x.startswith("data:")]
        text = next((x for x in lines if x.startswith("{")), "")
    try:
        result = json.loads(text)["result"]
        said = str(result["content"][0]["text"])
        failed = bool(result.get("isError"))
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        msg = f"unparsable MCP reply: {body[:80]!r}"
        raise TodoError(msg) from exc
    if failed:
        msg = f"tool refused: {said[:120]}"
        raise TodoError(msg)
    return said
