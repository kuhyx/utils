"""Tests for the SessionStart task summary."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

from todo_hooks import __main__ as cli
from todo_hooks.tests._fakes import TOKEN, FakeMcp, line

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import pytest

ORIGIN = "git@github.com:kuhyx/demo.git"


def _rows(count: int) -> str:
    return "\n".join(
        line(f"{i:08x}-x", "kuhyx/demo", f"# Task {i}") for i in range(count)
    )


def _env(mcp: FakeMcp) -> dict[str, str]:
    return {"TODO_MCP_URL": mcp.url, "TODO_MCP_TOKEN": TOKEN}


def _stdin(cwd: Path) -> str:
    return json.dumps({"cwd": str(cwd), "hook_event_name": "SessionStart"})


def test_prints_header_and_tasks(
    mcp: FakeMcp, make_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    root = make_repo("demo", origin=ORIGIN)
    seen: list[dict[str, object]] = []
    mcp.tools["list_tasks"] = lambda a: seen.append(a) or _rows(2)
    assert cli.main(["session-start"], env=_env(mcp), stdin=_stdin(root)) == 0
    assert capsys.readouterr().out.splitlines() == [
        "Open todo tasks for kuhyx/demo (2):",
        "- 00000000 Task 0",
        "- 00000001 Task 1",
    ]
    assert seen == [{"repo": "kuhyx/demo", "status": "open"}]


def test_nine_tasks_fit_ten_lines(
    mcp: FakeMcp, make_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    root = make_repo("demo", origin=ORIGIN)
    mcp.tools["list_tasks"] = lambda _a: _rows(9)
    cli.main(["session-start"], env=_env(mcp), stdin=_stdin(root))
    assert len(capsys.readouterr().out.splitlines()) == 10


def test_more_than_nine_is_truncated(
    mcp: FakeMcp, make_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    root = make_repo("demo", origin=ORIGIN)
    mcp.tools["list_tasks"] = lambda _a: _rows(15)
    cli.main(["session-start"], env=_env(mcp), stdin=_stdin(root))
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 10
    assert lines[0] == "Open todo tasks for kuhyx/demo (15):"
    assert lines[-1] == '… +7 more: list_tasks(repo="kuhyx/demo")'


def test_no_tasks_prints_nothing(
    mcp: FakeMcp, make_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    root = make_repo("demo", origin=ORIGIN)
    mcp.tools["list_tasks"] = lambda _a: "no tasks match"
    assert cli.main(["session-start"], env=_env(mcp), stdin=_stdin(root)) == 0
    assert capsys.readouterr().out == ""


def test_cwd_fallback_when_stdin_is_not_json(
    mcp: FakeMcp, make_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    root = make_repo("demo", origin=ORIGIN)
    mcp.tools["list_tasks"] = lambda _a: _rows(1)
    cli.main(["session-start"], env=_env(mcp), cwd=root, stdin="not json")
    assert "kuhyx/demo" in capsys.readouterr().out
    cli.main(["session-start"], env=_env(mcp), cwd=root, stdin="[1]")
    assert "kuhyx/demo" in capsys.readouterr().out
    cli.main(["session-start"], env=_env(mcp), cwd=root, stdin="{}")
    assert "kuhyx/demo" in capsys.readouterr().out


def test_silent_without_git_or_origin(
    mcp: FakeMcp,
    make_repo: Callable[..., Path],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mcp.tools["list_tasks"] = lambda _a: _rows(1)
    plain = tmp_path / "plain"
    plain.mkdir()
    assert cli.main(["session-start"], env=_env(mcp), stdin=_stdin(plain)) == 0
    local = make_repo("local")
    assert cli.main(["session-start"], env=_env(mcp), stdin=_stdin(local)) == 0
    assert capsys.readouterr().out == ""
    assert mcp.requests == []


def test_silent_when_server_down_or_token_bad(
    mcp: FakeMcp, make_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    root = make_repo("demo", origin=ORIGIN)
    bad = {**_env(mcp), "TODO_MCP_TOKEN": "wrong"}
    assert cli.main(["session-start"], env=bad, stdin=_stdin(root)) == 0
    dead = {**_env(mcp), "TODO_MCP_URL": "http://127.0.0.1:1/mcp"}
    assert cli.main(["session-start"], env=dead, stdin=_stdin(root)) == 0
    no_token = {"TODO_MCP_URL": mcp.url, "TODO_MCP_TOKEN_FILE": "/nonexistent"}
    assert cli.main(["session-start"], env=no_token, stdin=_stdin(root)) == 0
    assert capsys.readouterr().out == ""


def test_silent_on_unexpected_error(
    mcp: FakeMcp, make_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    root = make_repo("demo", origin=ORIGIN)
    mcp.mode = "garbage"
    assert cli.main(["session-start"], env=_env(mcp), stdin=_stdin(root)) == 0
    assert capsys.readouterr().out == ""


def test_slow_server_stays_within_budget(
    mcp: FakeMcp, make_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    root = make_repo("demo", origin=ORIGIN)
    mcp.delay = 3.0
    mcp.tools["list_tasks"] = lambda _a: _rows(1)
    start = time.monotonic()
    assert cli.main(["session-start"], env=_env(mcp), stdin=_stdin(root)) == 0
    assert time.monotonic() - start < 1.6
    assert capsys.readouterr().out == ""
