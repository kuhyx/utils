"""Tests for the CLI dispatcher and the trust subcommand."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

from todo_hooks import __main__ as cli
from todo_hooks import trust_cmd
from todo_hooks.client import McpToolError, McpUnavailable
from todo_hooks.tests._fakes import (
    TOKEN,
    FakeClient,
    FakeMcp,
    detail,
    line,
    task_client,
)
from todo_hooks.trust import check_hash, is_trusted

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from todo_hooks.context import Context
    from todo_hooks.paths import Paths

ID = "0123abcd-0000-4000-8000-000000000001"
ID2 = "4567ef01-0000-4000-8000-000000000002"


def test_trust_one(
    make_ctx: Callable[..., tuple[Context, list[str]]], paths: Paths, tmp_path: Path
) -> None:
    client = task_client(detail(ID, done_check="make test"))
    ctx, out = make_ctx(client, tmp_path)
    assert trust_cmd.run(ctx, ["0123abcd"]) == 0
    assert is_trusted(paths.trust_file, "make test")
    assert out == [
        f"todo-hooks: trusted 0123abcd (sha256 {check_hash('make test')[:12]})"
    ]


def test_trust_one_failures(
    make_ctx: Callable[..., tuple[Context, list[str]]], tmp_path: Path
) -> None:
    ctx, out = make_ctx(task_client(detail(ID, done_check=None)), tmp_path)
    assert trust_cmd.run(ctx, ["0123abcd"]) == 1
    assert "has no done_check" in out[-1]
    assert trust_cmd.run(ctx, ["ffffffff"]) == 1
    assert "not found" in out[-1]
    assert trust_cmd.run(ctx, []) == 2
    assert "usage" in out[-1]
    assert trust_cmd.run(ctx, ["a", "b"]) == 2


def test_trust_server_down(
    make_ctx: Callable[..., tuple[Context, list[str]]], tmp_path: Path
) -> None:
    ctx, out = make_ctx(FakeClient({"get_task": McpUnavailable("refused")}), tmp_path)
    assert trust_cmd.run(ctx, ["0123abcd"]) == 1
    assert "unavailable" in out[-1]


def test_seed_open_trusts_all_open_with_checks(
    make_ctx: Callable[..., tuple[Context, list[str]]], paths: Paths, tmp_path: Path
) -> None:
    client = task_client(
        detail(ID, done_check="first"),
        detail(ID2, done_check=None),
        list_tasks="\n".join([line(ID), line(ID2), "garbage"]),
    )
    ctx, out = make_ctx(client, tmp_path)
    assert trust_cmd.run(ctx, ["--seed-open"]) == 0
    assert is_trusted(paths.trust_file, "first")
    assert out[-1] == "todo-hooks: seeded 1 new check(s) from 2 open note(s)"
    # Re-seeding is idempotent.
    assert trust_cmd.run(ctx, ["--seed-open"]) == 0
    assert out[-1] == "todo-hooks: seeded 0 new check(s) from 2 open note(s)"
    assert client.calls[0] == ("list_tasks", {"status": "open"})


def test_seed_open_tool_error(
    make_ctx: Callable[..., tuple[Context, list[str]]], tmp_path: Path
) -> None:
    ctx, out = make_ctx(FakeClient({"list_tasks": McpToolError("error: x")}), tmp_path)
    assert trust_cmd.run(ctx, ["--seed-open"]) == 1
    assert "error: x" in out[-1]


def test_main_usage_and_unknown(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([]) == 2
    assert cli.main(["wat"]) == 2
    assert "usage: python3 -m todo_hooks" in capsys.readouterr().out


def test_main_closer_end_to_end_against_fake_server(
    mcp: FakeMcp,
    make_repo: Callable[..., Path],
    paths: Paths,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = make_repo(
        "demo", origin="git@github.com:kuhyx/demo.git", message="x\n\nTodo: 0123abcd"
    )
    mcp.tools["get_task"] = lambda _a: detail(ID, done_check="true")
    closed: list[dict[str, object]] = []
    mcp.tools["close_task"] = lambda a: closed.append(a) or "closed"
    env = {
        "TODO_MCP_URL": mcp.url,
        "TODO_MCP_TOKEN": TOKEN,
        "TODO_HOOKS_TRUST_FILE": str(paths.trust_file),
    }
    assert cli.main(["trust", "0123abcd"], env=env, cwd=root) == 0
    assert cli.main(["closer"], env=env, cwd=root) == 0
    assert closed[0]["id"] == ID
    assert "closed 0123abcd" in capsys.readouterr().out


def test_main_closer_without_token_fails_open(
    make_repo: Callable[..., Path], paths: Paths, capsys: pytest.CaptureFixture[str]
) -> None:
    root = make_repo("demo", message="x\n\nTodo: 0123abcd")
    env = {"TODO_MCP_TOKEN_FILE": str(paths.token_file)}
    assert cli.main(["closer"], env=env, cwd=root) == 0
    assert "warning" in capsys.readouterr().out


def test_main_sweep_flags(
    mcp: FakeMcp,
    paths: Paths,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mcp.tools["list_tasks"] = lambda _a: "no tasks match"
    env = {"TODO_MCP_URL": mcp.url, "TODO_MCP_TOKEN": TOKEN}
    report = tmp_path / "r.txt"
    args = [
        "sweep",
        "--report",
        str(report),
        "--dry-run",
        "--trust-file",
        str(tmp_path / "t"),
    ]
    assert cli.main(args, env=env, cwd=tmp_path) == 0
    assert report.read_text().startswith("# dry-run: 0 open notes")
    assert "dry-run" in capsys.readouterr().out
    assert cli.main(["sweep", "--bogus"], env=env, cwd=tmp_path) == 2


def test_main_import_pr_dispatch(
    make_repo: Callable[..., Path],
    paths: Paths,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo("demo", origin="git@github.com:kuhyx/demo.git")
    monkeypatch.setattr("todo_hooks.gh.run_gh", lambda _a: "[]")
    env = {"TODO_MCP_TOKEN_FILE": str(paths.token_file)}
    assert cli.main(["import-pr", "post-merge"], env=env, cwd=root, stdin="") == 0


def test_module_entrypoint_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["todo_hooks"])
    monkeypatch.delitem(sys.modules, "todo_hooks.__main__", raising=False)
    import runpy

    with pytest.raises(SystemExit) as info:
        runpy.run_module("todo_hooks", run_name="__main__", alter_sys=True)
    assert info.value.code == 2
