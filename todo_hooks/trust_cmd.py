"""``trust <id>`` and ``trust --seed-open``: approve done_checks for execution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from todo_hooks.client import McpError, McpToolError
from todo_hooks.context import describe
from todo_hooks.notes import parse_detail, parse_list
from todo_hooks.trust import add_trusted, check_hash

if TYPE_CHECKING:
    from todo_hooks.client import TaskClient
    from todo_hooks.context import Context

USAGE = "usage: python3 -m todo_hooks trust <id8> | --seed-open"


def _trust_one(ctx: Context, client: TaskClient, task_id: str) -> int:
    try:
        task = parse_detail(client.call("get_task", {"id": task_id}))
    except McpToolError as err:
        ctx.say(f"{task_id} not found: {err}")
        return 1
    if not task.done_check:
        ctx.say(f"{task_id} has no done_check; nothing to trust")
        return 1
    add_trusted(ctx.paths.trust_file, task.done_check, f"{task_id[:8]} {task.repo}")
    ctx.say(f"trusted {task_id[:8]} (sha256 {check_hash(task.done_check)[:12]})")
    return 0


def _seed_open(ctx: Context, client: TaskClient) -> int:
    rows = parse_list(client.call("list_tasks", {"status": "open"}))
    added = 0
    for row in rows:
        task = parse_detail(client.call("get_task", {"id": row.id8}))
        if task.done_check:
            label = f"{row.id8} {row.repo}"
            added += add_trusted(ctx.paths.trust_file, task.done_check, label)
    ctx.say(f"seeded {added} new check(s) from {len(rows)} open note(s)")
    return 0


def run(ctx: Context, args: list[str]) -> int:
    """Trust one note's check, or every currently open one."""
    if len(args) != 1:
        ctx.out(USAGE)
        return 2
    try:
        client = ctx.make_client()
        try:
            if args[0] == "--seed-open":
                return _seed_open(ctx, client)
            return _trust_one(ctx, client, args[0])
        finally:
            client.close()
    except McpError as err:
        ctx.say(f"trust failed: {describe(err)}")
        return 1
