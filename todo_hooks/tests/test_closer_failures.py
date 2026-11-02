"""Tests for the closer when the server or the close call misbehaves."""

from __future__ import annotations

from typing import TYPE_CHECKING

from todo_hooks import closer
from todo_hooks.client import McpAuthError, McpToolError, McpUnavailable
from todo_hooks.tests._closer_helpers import ID, ID2, MSG
from todo_hooks.tests._closer_helpers import setup as _setup
from todo_hooks.tests._fakes import FakeClient, detail, task_client
from todo_hooks.trust import add_trusted

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from todo_hooks.context import Context
    from todo_hooks.paths import Paths


def test_unknown_id_is_reported_and_next_continues(
    make_repo: Callable[..., Path],
    make_ctx: Callable[..., tuple[Context, list[str]]],
    paths: Paths,
) -> None:
    client = task_client(detail(ID2))
    msg = "feat\n\nTodo: 0123abcd\nTodo: 4567ef01"
    _, ctx, lines = _setup(make_repo, make_ctx, paths, client, message=msg)
    closer.run(ctx)
    assert lines[0].startswith("todo-hooks: 0123abcd not found")
    assert lines[1] == "todo-hooks: closed 4567ef01"


def test_server_down_warns_once_and_exits_zero(
    make_repo: Callable[..., Path],
    make_ctx: Callable[..., tuple[Context, list[str]]],
    paths: Paths,
) -> None:
    client = FakeClient({"get_task": McpUnavailable("connection refused")})
    msg = "feat\n\nTodo: 0123abcd\nTodo: 4567ef01"
    _, ctx, lines = _setup(make_repo, make_ctx, paths, client, message=msg)
    assert closer.run(ctx) == 0
    assert client.tools() == ["get_task"]
    assert lines == [
        "todo-hooks: warning: todo server unavailable (connection refused); nothing closed"
    ]


def test_auth_failure_warns(
    make_repo: Callable[..., Path],
    make_ctx: Callable[..., tuple[Context, list[str]]],
    paths: Paths,
) -> None:
    client = FakeClient({"get_task": McpAuthError("bad token")})
    _, ctx, lines = _setup(make_repo, make_ctx, paths, client)
    assert closer.run(ctx) == 0
    assert len(lines) == 1
    assert "warning" in lines[0]
    assert "bad token" in lines[0]


def test_client_construction_failure_warns(
    make_repo: Callable[..., Path],
    make_ctx: Callable[..., tuple[Context, list[str]]],
    paths: Paths,
) -> None:
    _, ctx, lines = _setup(make_repo, make_ctx, paths, FakeClient())

    def boom() -> FakeClient:
        raise McpAuthError("no token")

    ctx.make_client = boom  # type: ignore[assignment]
    assert closer.run(ctx) == 0
    assert "no token" in lines[0]


def test_close_refused_warns(
    make_repo: Callable[..., Path],
    make_ctx: Callable[..., tuple[Context, list[str]]],
    paths: Paths,
) -> None:
    client = task_client(
        detail(ID), close_task=McpToolError("error: evidence: required")
    )
    _, ctx, lines = _setup(make_repo, make_ctx, paths, client)
    closer.run(ctx)
    assert lines == ["todo-hooks: 0123abcd close failed: error: evidence: required"]


def test_no_remote_uses_toplevel_basename(
    make_repo: Callable[..., Path],
    make_ctx: Callable[..., tuple[Context, list[str]]],
    paths: Paths,
) -> None:
    root = make_repo("solo", message=MSG)
    add_trusted(paths.trust_file, "true", "t")
    client = task_client(detail(ID, repo="kuhyx/solo"))
    ctx, _ = make_ctx(client, root)
    closer.run(ctx)
    assert "close_task" in client.tools()
