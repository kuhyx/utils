"""``python3 -m todo_hooks {closer|sweep|trust|import-pr}``."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from todo_hooks import closer, import_pr, session_start, sweep, trust_cmd
from todo_hooks.context import Context

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

    from todo_hooks.client import TaskClient

USAGE = (
    "usage: python3 -m todo_hooks {closer|sweep|trust|import-pr|session-start} [args]"
)


def main(
    argv: list[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
    stdin: str | None = None,
    make_client: Callable[[], TaskClient] | None = None,
) -> int:
    """Dispatch one subcommand; returns the process exit code."""
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in {
        "closer",
        "sweep",
        "trust",
        "import-pr",
        "session-start",
    }:
        print(USAGE)
        return 2
    budget = session_start.BUDGET_SECONDS if args[0] == "session-start" else None
    ctx = Context.build(env, cwd, make_client, budget)
    command, rest = args[0], args[1:]
    if command == "closer":
        return closer.run(ctx)
    if command == "session-start":
        return session_start.run(ctx, sys.stdin.read() if stdin is None else stdin)
    if command == "sweep":
        return sweep.main(ctx, rest)
    if command == "trust":
        return trust_cmd.run(ctx, rest)
    return import_pr.run(ctx, rest, stdin=stdin)


if __name__ == "__main__":
    sys.exit(main())
