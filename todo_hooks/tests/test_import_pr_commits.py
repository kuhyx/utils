"""Tests for choosing which commits to scan, and the hook entry point."""

from __future__ import annotations

from typing import TYPE_CHECKING

from todo_hooks import gh, import_pr
from todo_hooks.tests._fakes import FakeGh, line, make_pr
from todo_hooks.tests._pr_helpers import pr_repo, search_client
from todo_hooks.tests.conftest import git

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import pytest

    from todo_hooks.context import Context


def test_commits_post_merge_uses_orig_head(make_repo: Callable[..., Path]) -> None:
    root = pr_repo(make_repo, 2)
    old = git(root, "rev-parse", "HEAD~2")
    git(root, "update-ref", "ORIG_HEAD", old)
    shas = import_pr.commits_post_merge(root)
    assert shas == git(root, "rev-list", "ORIG_HEAD..HEAD").splitlines()
    assert len(shas) == 2


def test_commits_post_merge_without_orig_head(make_repo: Callable[..., Path]) -> None:
    assert import_pr.commits_post_merge(make_repo()) == []


def test_commits_post_merge_is_capped(
    make_repo: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = pr_repo(make_repo, 3)
    git(root, "update-ref", "ORIG_HEAD", git(root, "rev-parse", "HEAD~3"))
    monkeypatch.setattr(import_pr, "MAX_COMMITS", 2)
    assert len(import_pr.commits_post_merge(root)) == 2


def test_commits_post_rewrite_only_for_rebase(make_repo: Callable[..., Path]) -> None:
    root = pr_repo(make_repo, 1)
    pairs = "oldsha1 newsha1\noldsha2 newsha2 extra\n\n"
    assert import_pr.commits_post_rewrite(root, "rebase", pairs) == [
        "newsha1",
        "newsha2",
    ]
    assert import_pr.commits_post_rewrite(root, "amend", pairs) == []
    assert import_pr.commits_post_rewrite(root, "", pairs) == []


def test_commits_post_rewrite_without_stdin_falls_back(
    make_repo: Callable[..., Path],
) -> None:
    root = pr_repo(make_repo, 2)
    git(root, "update-ref", "ORIG_HEAD", git(root, "rev-parse", "HEAD~2"))
    assert len(import_pr.commits_post_rewrite(root, "rebase", "")) == 2


def test_main_post_merge_end_to_end(
    make_repo: Callable[..., Path], make_ctx: Callable[..., tuple[Context, list[str]]]
) -> None:
    root = pr_repo(make_repo, 1)
    sha = git(root, "rev-parse", "HEAD")
    git(root, "update-ref", "ORIG_HEAD", git(root, "rev-parse", "HEAD~1"))
    client = search_client()
    ctx, _ = make_ctx(client, root)
    assert (
        import_pr.run(ctx, ["post-merge"], FakeGh({sha: [make_pr(9)]}), stdin="") == 0
    )
    assert client.tools().count("add_task") == 3


def test_main_post_rewrite_uses_env_command(
    make_repo: Callable[..., Path], make_ctx: Callable[..., tuple[Context, list[str]]]
) -> None:
    root = pr_repo(make_repo, 1)
    sha = git(root, "rev-parse", "HEAD")
    client = search_client()
    ctx, _ = make_ctx(client, root, {"PRE_COMMIT_REWRITE_COMMAND": "rebase"})
    assert (
        import_pr.run(
            ctx, ["post-rewrite"], FakeGh({sha: [make_pr(9)]}), stdin=f"old {sha}\n"
        )
        == 0
    )
    assert client.tools().count("add_task") == 3


def test_main_explicit_range_and_bad_mode(
    make_repo: Callable[..., Path], make_ctx: Callable[..., tuple[Context, list[str]]]
) -> None:
    root = pr_repo(make_repo, 1)
    sha = git(root, "rev-parse", "HEAD")
    client = search_client()
    ctx, out = make_ctx(client, root)
    assert (
        import_pr.run(
            ctx, ["--range", "HEAD~1..HEAD"], FakeGh({sha: [make_pr(9)]}), stdin=""
        )
        == 0
    )
    assert client.tools().count("add_task") == 3
    assert import_pr.run(ctx, ["bogus"], FakeGh({}), stdin="") == 2
    assert "usage" in out[-1]


def test_not_in_git_repo_is_quiet(
    tmp_path: Path, make_ctx: Callable[..., tuple[Context, list[str]]]
) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    ctx, out = make_ctx(search_client(), plain)
    assert import_pr.run(ctx, ["post-merge"], FakeGh({}), stdin="") == 0
    assert out == []


def test_read_stdin_variants(monkeypatch: pytest.MonkeyPatch) -> None:
    import io
    import os

    read_end, write_end = os.pipe()
    os.write(write_end, b"old new\n")
    os.close(write_end)
    monkeypatch.setattr("sys.stdin", os.fdopen(read_end, "r"))
    assert import_pr.read_stdin() == "old new\n"

    idle_read, idle_write = os.pipe()
    monkeypatch.setattr("sys.stdin", os.fdopen(idle_read, "r"))
    assert import_pr.read_stdin(timeout=0.05) == ""
    os.close(idle_write)

    monkeypatch.setattr("sys.stdin", io.StringIO("no fileno"))
    assert import_pr.read_stdin() == ""


def test_run_post_rewrite_reads_real_stdin_when_not_given(
    make_repo: Callable[..., Path],
    make_ctx: Callable[..., tuple[Context, list[str]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = pr_repo(make_repo, 1)
    monkeypatch.setattr(import_pr, "read_stdin", lambda: "")
    ctx, out = make_ctx(search_client(), root, {})
    assert import_pr.run(ctx, ["post-rewrite", "amend"], FakeGh({})) == 0
    assert out == []


def test_nothing_new_to_import_is_silent(
    make_repo: Callable[..., Path], make_ctx: Callable[..., tuple[Context, list[str]]]
) -> None:
    root = pr_repo(make_repo, 1)
    sha = git(root, "rev-parse", "HEAD")
    existing = "\n".join(
        line("abcdef12-x", "kuhyx/demo", f"# {t}")
        for t in ("Add retry to sync", "Document the flag", "Star bullet")
    )
    ctx, out = make_ctx(search_client(existing), root)
    assert import_pr.import_for_commits(ctx, [sha], FakeGh({sha: [make_pr(7)]})) == 0
    assert out == []


def test_rewrite_includes_upstream_commits_after_pull_rebase(tmp_path: Path) -> None:
    upstream = tmp_path / "up.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(upstream))
    mine, other = tmp_path / "mine", tmp_path / "other"
    git(tmp_path, "clone", "-q", str(upstream), str(mine))
    (mine / "a").write_text("a")
    git(mine, "add", "a")
    git(mine, "commit", "-q", "-m", "base")
    git(mine, "push", "-q", "origin", "HEAD:main")
    git(tmp_path, "clone", "-q", str(upstream), str(other))
    (other / "b").write_text("b")
    git(other, "add", "b")
    git(other, "commit", "-q", "-m", "arrives via pull")
    git(other, "push", "-q", "origin", "HEAD:main")
    arrived = git(other, "rev-parse", "HEAD")
    (mine / "c").write_text("c")
    git(mine, "add", "c")
    git(mine, "commit", "-q", "-m", "local only")
    git(mine, "pull", "-q", "--rebase", "origin", "main")
    replayed = git(mine, "rev-parse", "HEAD")
    shas = import_pr.commits_post_rewrite(mine, "rebase", f"old {replayed}\n")
    assert arrived in shas
    assert shas.count(replayed) == 1


def test_unpushed_commit_does_not_stop_the_scan(
    make_repo: Callable[..., Path],
    make_ctx: Callable[..., tuple[Context, list[str]]],
) -> None:
    root = pr_repo(make_repo, 1)
    fake = FakeGh({"known": [make_pr(7)]})

    def runner(args: list[str]) -> str:
        if "unpushed" in args[1]:
            raise gh.GhNotFound("No commit found (HTTP 422)")
        return fake(args)

    client = search_client()
    ctx, _ = make_ctx(client, root)
    assert import_pr.import_for_commits(ctx, ["unpushed", "known"], runner) == 3
