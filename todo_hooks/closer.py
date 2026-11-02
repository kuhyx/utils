"""Post-commit closer: close ``Todo:`` trailer tasks whose check passes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from todo_hooks.checkrun import CHECK_TIMEOUT, run_check
from todo_hooks.client import McpError, McpToolError
from todo_hooks.context import describe
from todo_hooks.gitrepo import expected_repo, head_sha, head_todo_ids, toplevel
from todo_hooks.notes import Task, parse_detail
from todo_hooks.trust import is_trusted

if TYPE_CHECKING:
    from pathlib import Path

    from todo_hooks.client import TaskClient
    from todo_hooks.context import Context


def _refusal(ctx: Context, root: Path, task: Task) -> str | None:
    """Why this task must not be auto-closed, or None when it may run."""
    expected = expected_repo(root)
    id8 = task.id[:8]
    if task.status == "done":
        return f"{id8} already done"
    if task.repo != expected:
        return f"{id8} belongs to {task.repo or 'no repo'}, not {expected}; left open"
    if task.is_manual:
        return f"{id8} close by hand (Check: manual)"
    if not task.done_check:
        return f"{id8} has no done_check; close by hand"
    if not is_trusted(ctx.paths.trust_file, task.done_check):
        return f"{id8} untrusted done_check; run: python3 -m todo_hooks trust {id8}"
    return None


def _verdict(ctx: Context, root: Path, task_id: str, client: TaskClient) -> str:
    """One line saying what happened to the task; closes it on a trusted pass."""
    try:
        task = parse_detail(client.call("get_task", {"id": task_id}))
    except McpToolError as err:
        return f"{task_id[:8]} not found: {err}"
    refusal = _refusal(ctx, root, task)
    if refusal:
        return refusal
    result = run_check(task.done_check or "", root, timeout=CHECK_TIMEOUT)
    if not result.passed:
        return f"{task.id[:8]} left open: done_check {result.describe()}"
    evidence = f"{head_sha(root)} done_check exit 0"
    try:
        client.call("close_task", {"id": task.id, "evidence": evidence})
    except McpToolError as err:
        return f"{task.id[:8]} close failed: {err}"
    return f"closed {task.id[:8]}"


def run(ctx: Context) -> int:
    """Always 0: the commit already happened, so a failure here must stay quiet."""
    root = toplevel(ctx.cwd)
    ids = head_todo_ids(root) if root else []
    if root is None or not ids:
        return 0
    try:
        client = ctx.make_client()
    except McpError as err:
        ctx.say(f"warning: {describe(err)}; nothing closed")
        return 0
    try:
        for task_id in ids:
            ctx.say(_verdict(ctx, root, task_id, client))
    except McpError as err:
        ctx.say(f"warning: {describe(err)}; nothing closed")
    finally:
        client.close()
    return 0
