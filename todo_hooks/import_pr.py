"""Import ``## Todo:`` items from the PRs of newly pulled commits as tasks."""

from __future__ import annotations

import select
import sys
from typing import TYPE_CHECKING

from todo_hooks import gh
from todo_hooks.client import McpError
from todo_hooks.context import describe
from todo_hooks.gitrepo import expected_repo, git, origin_slug, toplevel
from todo_hooks.notes import parse_list
from todo_hooks.pr_parse import TodoItem, parse_todo_items

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from todo_hooks.client import TaskClient
    from todo_hooks.context import Context

MAX_COMMITS = 30
_PAIR_FIELDS = 2
USAGE = (
    "usage: python3 -m todo_hooks import-pr "
    "post-merge | post-rewrite [rebase] | --range A..B"
)


def _rev_list(root: Path, spec: str) -> list[str]:
    out = git(root, "rev-list", f"--max-count={MAX_COMMITS}", spec)
    return out.splitlines() if out else []


def commits_post_merge(root: Path) -> list[str]:
    """Commits a pull brought in: ORIG_HEAD..HEAD."""
    return _rev_list(root, "ORIG_HEAD..HEAD")


def commits_post_rewrite(root: Path, command: str, pairs: str) -> list[str]:
    """Rebase only: ORIG_HEAD..HEAD plus the new shas of stdin ``old new`` lines."""
    if command != "rebase":
        return []
    shas = commits_post_merge(root)
    for row in pairs.splitlines():
        fields = row.split()
        if len(fields) >= _PAIR_FIELDS and fields[1] not in shas:
            shas.append(fields[1])
    return shas[:MAX_COMMITS]


def read_stdin(timeout: float = 1.0) -> str:
    """Stdin text if any arrives within `timeout`; never blocks a hook."""
    try:
        ready, _, _ = select.select([sys.stdin], [], [], timeout)
    except ValueError, OSError:
        return ""
    return sys.stdin.read() if ready else ""


def _exists(client: TaskClient, repo: str, number: int, item: TodoItem) -> bool:
    found = parse_list(client.call("search_tasks", {"query": f"PR #{number}"}))
    return any(r.repo == repo and r.title == item.title for r in found)


def _add(client: TaskClient, repo: str, number: int, item: TodoItem) -> bool:
    if _exists(client, repo, number, item):
        return False
    args = {
        "repo": repo,
        "title": item.title,
        "body": f"Imported from PR #{number} of {repo}.",
        "priority": "medium",
    }
    if item.done_check:
        args["done_check"] = item.done_check
    client.call("add_task", args)
    return True


def _prs_of(
    slug: tuple[str, str], sha: str, runner: Callable[[list[str]], str] | None
) -> list[gh.PullRequest]:
    try:
        return gh.merged_prs(slug[0], slug[1], sha, runner)
    except gh.GhNotFound:
        return []


def import_for_commits(
    ctx: Context, shas: list[str], runner: Callable[[list[str]], str] | None
) -> int:
    """Add a task per new ``## Todo:`` item; warns and returns on gh/server failure."""
    root = toplevel(ctx.cwd)
    if not shas or root is None:
        return 0
    slug = origin_slug(root)
    if slug is None:
        ctx.say("no GitHub origin; PR import skipped")
        return 0
    repo, seen, total = expected_repo(root), set(), 0
    client: TaskClient | None = None
    try:
        for sha in shas:
            for pr in _prs_of(slug, sha, runner):
                items = parse_todo_items(pr.body)
                if not pr.merged or pr.number in seen or not items:
                    continue
                seen.add(pr.number)
                client = client or ctx.make_client()
                added = sum(_add(client, repo, pr.number, item) for item in items)
                if added:
                    ctx.say(f"imported {added} task(s) from PR #{pr.number}")
                total += added
    except gh.GhError as err:
        ctx.say(f"warning: gh unavailable ({err}); PR import skipped")
    except McpError as err:
        ctx.say(f"warning: {describe(err)}; PR import skipped")
    finally:
        if client:
            client.close()
    return total


def run(
    ctx: Context,
    args: list[str],
    gh_runner: Callable[[list[str]], str] | None = None,
    stdin: str | None = None,
) -> int:
    """Hook entry: always 0 except a usage error (2)."""
    mode = args[0] if args else "post-merge"
    root = toplevel(ctx.cwd)
    if mode == "--range" and len(args) == 2:  # noqa: PLR2004
        shas = _rev_list(root, args[1]) if root else []
    elif mode == "post-merge":
        shas = commits_post_merge(root) if root else []
    elif mode == "post-rewrite":
        command = (
            args[1] if len(args) > 1 else ctx.env.get("PRE_COMMIT_REWRITE_COMMAND", "")
        )
        pairs = read_stdin() if stdin is None else stdin
        shas = commits_post_rewrite(root, command, pairs) if root else []
    else:
        ctx.out(USAGE)
        return 2
    import_for_commits(ctx, shas, gh_runner)
    return 0
