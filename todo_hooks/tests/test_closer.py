"""Tests for the post-commit closer."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from todo_hooks import closer
from todo_hooks.tests._fakes import detail, task_client
from todo_hooks.tests.conftest import git

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from todo_hooks.context import Context
    from todo_hooks.paths import Paths

from todo_hooks.tests._closer_helpers import ID
from todo_hooks.tests._closer_helpers import setup as _setup


def test_no_trailers_never_contacts_server(
    make_repo: Callable[..., Path], make_ctx: Callable[..., tuple[Context, list[str]]]
) -> None:
    root = make_repo()
    ctx, lines = make_ctx(None, root)
    ctx.make_client = lambda: pytest.fail("client built without trailers")  # type: ignore[assignment,return-value]
    assert closer.run(ctx) == 0
    assert lines == []


def test_not_a_git_repo_is_silent(
    tmp_path: Path, make_ctx: Callable[..., tuple[Context, list[str]]]
) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    ctx, lines = make_ctx(None, plain)
    assert closer.run(ctx) == 0
    assert lines == []


def test_closes_on_exit_zero(
    make_repo: Callable[..., Path],
    make_ctx: Callable[..., tuple[Context, list[str]]],
    paths: Paths,
) -> None:
    client = task_client(detail(ID, done_check="true"))
    root, ctx, lines = _setup(make_repo, make_ctx, paths, client)
    assert closer.run(ctx) == 0
    sha = git(root, "rev-parse", "--short=7", "HEAD")
    assert client.calls[-1] == (
        "close_task",
        {"id": ID, "evidence": f"{sha} done_check exit 0"},
    )
    assert lines == ["todo-hooks: closed 0123abcd"]


def test_runs_from_repo_root_even_in_subdir(
    make_repo: Callable[..., Path],
    make_ctx: Callable[..., tuple[Context, list[str]]],
    paths: Paths,
) -> None:
    check = "test -f f.txt"
    client = task_client(detail(ID, done_check=check))
    root, ctx, _ = _setup(make_repo, make_ctx, paths, client, check=check)
    (root / "sub").mkdir()
    ctx.cwd = root / "sub"
    closer.run(ctx)
    assert "close_task" in client.tools()


def test_nonzero_leaves_open(
    make_repo: Callable[..., Path],
    make_ctx: Callable[..., tuple[Context, list[str]]],
    paths: Paths,
) -> None:
    client = task_client(detail(ID, done_check="exit 4"))
    _, ctx, lines = _setup(make_repo, make_ctx, paths, client, check="exit 4")
    closer.run(ctx)
    assert "close_task" not in client.tools()
    assert lines == ["todo-hooks: 0123abcd left open: done_check exit 4"]


def test_timeout_leaves_open(
    make_repo: Callable[..., Path],
    make_ctx: Callable[..., tuple[Context, list[str]]],
    paths: Paths,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(closer, "CHECK_TIMEOUT", 0.3)
    client = task_client(detail(ID, done_check="sleep 20"))
    _, ctx, lines = _setup(make_repo, make_ctx, paths, client, check="sleep 20")
    closer.run(ctx)
    assert "close_task" not in client.tools()
    assert "timed out" in lines[0]


def test_untrusted_check_is_not_executed(
    make_repo: Callable[..., Path],
    make_ctx: Callable[..., tuple[Context, list[str]]],
    paths: Paths,
    tmp_path: Path,
) -> None:
    marker = tmp_path / "ran"
    check = f"touch {marker}"
    client = task_client(detail(ID, done_check=check))
    _, ctx, lines = _setup(make_repo, make_ctx, paths, client, check=check, trust=False)
    closer.run(ctx)
    assert not marker.exists()
    assert "close_task" not in client.tools()
    assert lines == [
        "todo-hooks: 0123abcd untrusted done_check; run: python3 -m todo_hooks trust 0123abcd"
    ]


def test_repo_mismatch_is_not_executed(
    make_repo: Callable[..., Path],
    make_ctx: Callable[..., tuple[Context, list[str]]],
    paths: Paths,
) -> None:
    client = task_client(detail(ID, repo="kuhyx/other"))
    _, ctx, lines = _setup(make_repo, make_ctx, paths, client)
    closer.run(ctx)
    assert "close_task" not in client.tools()
    assert "belongs to kuhyx/other, not kuhyx/demo" in lines[0]


def test_note_without_repo_is_mismatch(
    make_repo: Callable[..., Path],
    make_ctx: Callable[..., tuple[Context, list[str]]],
    paths: Paths,
) -> None:
    raw = f"id: {ID}\nstatus: todo\ndone_check: true\n---\nT"
    client = task_client(raw)
    _, ctx, lines = _setup(make_repo, make_ctx, paths, client)
    closer.run(ctx)
    assert "close_task" not in client.tools()
    assert "no repo" in lines[0]


def test_manual_note_is_listed_not_closed(
    make_repo: Callable[..., Path],
    make_ctx: Callable[..., tuple[Context, list[str]]],
    paths: Paths,
) -> None:
    client = task_client(detail(ID, text="# T\n\nCheck: manual"))
    _, ctx, lines = _setup(make_repo, make_ctx, paths, client)
    closer.run(ctx)
    assert "close_task" not in client.tools()
    assert lines == ["todo-hooks: 0123abcd close by hand (Check: manual)"]


def test_note_without_done_check(
    make_repo: Callable[..., Path],
    make_ctx: Callable[..., tuple[Context, list[str]]],
    paths: Paths,
) -> None:
    client = task_client(detail(ID, done_check=None))
    _, ctx, lines = _setup(make_repo, make_ctx, paths, client, check=None)
    closer.run(ctx)
    assert lines == ["todo-hooks: 0123abcd has no done_check; close by hand"]


def test_already_done_is_skipped(
    make_repo: Callable[..., Path],
    make_ctx: Callable[..., tuple[Context, list[str]]],
    paths: Paths,
) -> None:
    client = task_client(detail(ID, status="done"))
    _, ctx, lines = _setup(make_repo, make_ctx, paths, client)
    closer.run(ctx)
    assert "close_task" not in client.tools()
    assert lines == ["todo-hooks: 0123abcd already done"]
