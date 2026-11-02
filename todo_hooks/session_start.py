"""SessionStart hook: print the current repo's open tasks, at most ten lines."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from todo_hooks.gitrepo import expected_repo, origin_url, toplevel
from todo_hooks.notes import parse_list

if TYPE_CHECKING:
    from todo_hooks.context import Context

BUDGET_SECONDS = 0.8
MAX_LINES = 10


def _cwd_from(ctx: Context, stdin: str) -> Path:
    try:
        data = json.loads(stdin)
    except json.JSONDecodeError:
        return ctx.cwd
    cwd = data.get("cwd") if isinstance(data, dict) else None
    return Path(cwd) if cwd else ctx.cwd


def summary(repo: str, listing: str) -> list[str]:
    """Header plus task lines, truncated to MAX_LINES with a '+K more' tail."""
    rows = parse_list(listing)
    if not rows:
        return []
    out = [f"Open todo tasks for {repo} ({len(rows)}):"]
    shown = rows if len(rows) < MAX_LINES else rows[: MAX_LINES - 2]
    out += [f"- {row.id8} {row.title}" for row in shown]
    if len(shown) < len(rows):
        out.append(f'… +{len(rows) - len(shown)} more: list_tasks(repo="{repo}")')
    return out


def run(ctx: Context, stdin: str) -> int:
    """Always 0 and silent on any problem: a session must never wait on this."""
    try:
        root = toplevel(_cwd_from(ctx, stdin))
        if root is None or origin_url(root) is None:
            return 0
        repo = expected_repo(root)
        client = ctx.make_client()
        try:
            listing = client.call("list_tasks", {"repo": repo, "status": "open"})
        finally:
            client.close()
        for row in summary(repo, listing):
            ctx.out(row)
    except Exception:  # noqa: BLE001
        return 0
    return 0
