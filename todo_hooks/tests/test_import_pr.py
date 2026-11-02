"""Tests for the PR `## Todo:` importer."""

from __future__ import annotations

from typing import TYPE_CHECKING

from todo_hooks import gh, import_pr
from todo_hooks.client import McpUnavailable
from todo_hooks.tests._fakes import FakeClient, FakeGh, line, make_pr
from todo_hooks.tests._pr_helpers import pr_repo, search_client
from todo_hooks.tests.conftest import git

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from todo_hooks.context import Context


def test_import_adds_tasks_with_pr_reference(
    make_repo: Callable[..., Path], make_ctx: Callable[..., tuple[Context, list[str]]]
) -> None:
    root = pr_repo(make_repo, 1)
    sha = git(root, "rev-parse", "HEAD")
    client = search_client()
    ctx, out = make_ctx(client, root)
    count = import_pr.import_for_commits(ctx, [sha], FakeGh({sha: [make_pr(7)]}))
    assert count == 3
    adds = [a for t, a in client.calls if t == "add_task"]
    assert adds[0] == {
        "repo": "kuhyx/demo",
        "title": "Add retry to sync",
        "body": "Imported from PR #7 of kuhyx/demo.",
        "done_check": "pytest -q tests/test_retry.py",
        "priority": "medium",
    }
    assert "done_check" not in adds[1]
    assert "imported 3 task(s) from PR #7" in out[-1]


def test_dedupe_skips_same_pr_and_title(
    make_repo: Callable[..., Path], make_ctx: Callable[..., tuple[Context, list[str]]]
) -> None:
    root = pr_repo(make_repo, 1)
    sha = git(root, "rev-parse", "HEAD")
    existing = line("abcdef12-x", "kuhyx/demo", "# Document the flag")
    client = search_client(existing)
    ctx, _ = make_ctx(client, root)
    count = import_pr.import_for_commits(ctx, [sha], FakeGh({sha: [make_pr(7)]}))
    assert count == 2
    queries = [a["query"] for t, a in client.calls if t == "search_tasks"]
    assert queries == ["PR #7"] * 3
    titles = [a["title"] for t, a in client.calls if t == "add_task"]
    assert "Document the flag" not in titles


def test_same_pr_on_many_commits_imported_once(
    make_repo: Callable[..., Path], make_ctx: Callable[..., tuple[Context, list[str]]]
) -> None:
    root = pr_repo(make_repo, 2)
    shas = git(root, "rev-list", "HEAD").splitlines()
    client = search_client()
    ctx, _ = make_ctx(client, root)
    gh_fake = FakeGh({s: [make_pr(7)] for s in shas})
    assert import_pr.import_for_commits(ctx, shas, gh_fake) == 3


def test_unmerged_empty_and_bodyless_prs_are_ignored(
    make_repo: Callable[..., Path], make_ctx: Callable[..., tuple[Context, list[str]]]
) -> None:
    root = pr_repo(make_repo, 1)
    sha = git(root, "rev-parse", "HEAD")
    client = search_client()
    ctx, out = make_ctx(client, root)
    prs = [
        make_pr(1, merged=None),
        make_pr(2, body=None),
        make_pr(3, body="nothing here"),
    ]
    assert import_pr.import_for_commits(ctx, [sha], FakeGh({sha: prs})) == 0
    assert client.calls == []
    assert out == []


def test_non_github_origin_is_skipped(
    make_repo: Callable[..., Path], make_ctx: Callable[..., tuple[Context, list[str]]]
) -> None:
    root = make_repo("local", origin="/srv/local.git")
    ctx, out = make_ctx(search_client(), root)
    assert import_pr.import_for_commits(ctx, ["abc"], FakeGh({})) == 0
    assert "no GitHub origin" in out[0]


def test_gh_failure_warns_and_stops(
    make_repo: Callable[..., Path], make_ctx: Callable[..., tuple[Context, list[str]]]
) -> None:
    root = pr_repo(make_repo, 1)

    def broken(_args: list[str]) -> str:
        raise gh.GhError("gh not installed")

    ctx, out = make_ctx(search_client(), root)
    assert import_pr.import_for_commits(ctx, ["a", "b"], broken) == 0
    assert out == [
        "todo-hooks: warning: gh unavailable (gh not installed); PR import skipped"
    ]


def test_bad_gh_json_warns(
    make_repo: Callable[..., Path], make_ctx: Callable[..., tuple[Context, list[str]]]
) -> None:
    root = pr_repo(make_repo, 1)
    ctx, out = make_ctx(search_client(), root)
    assert import_pr.import_for_commits(ctx, ["a"], lambda _a: "{not json") == 0
    assert "PR import skipped" in out[0]


def test_server_down_warns_and_exits_cleanly(
    make_repo: Callable[..., Path], make_ctx: Callable[..., tuple[Context, list[str]]]
) -> None:
    root = pr_repo(make_repo, 1)
    sha = git(root, "rev-parse", "HEAD")
    client = FakeClient({"search_tasks": McpUnavailable("refused")})
    ctx, out = make_ctx(client, root)
    assert import_pr.import_for_commits(ctx, [sha], FakeGh({sha: [make_pr(7)]})) == 0
    assert out == [
        "todo-hooks: warning: todo server unavailable (refused); PR import skipped"
    ]
