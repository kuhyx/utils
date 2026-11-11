# Copyright (c) 2026 Krzysztof Rudnicki
"""``feedback-inbox run | sync``: what the systemd units execute."""

from __future__ import annotations

import argparse
import fcntl
import logging
import time
from typing import TYPE_CHECKING

from feedback_inbox._inbox import Importer, Outcome, Waiter, run_settled
from feedback_inbox._paths import resolve_paths
from feedback_inbox._todo import McpTodoClient
from feedback_inbox._units import run_systemctl, sync_units

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from feedback_inbox._todo import TodoClient

LOG = logging.getLogger("feedback_inbox")
OWNER = "kuhyx"
DEFAULT_WAIT = 15.0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="feedback-inbox")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="import new bundles as todo tasks")
    run.add_argument("--wait", type=float, default=DEFAULT_WAIT)
    sub.add_parser("sync", help="re-arm the path units for the current games")
    return parser


def _run(wait: float, client: TodoClient | None) -> int:
    paths = resolve_paths()
    todo = client or McpTodoClient(paths.mcp_url, paths.token_file)
    paths.lock_file.parent.mkdir(parents=True, exist_ok=True)
    # Blocking lock: a second run waits, then finds the markers and skips.
    with paths.lock_file.open("a", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        results = run_settled(
            paths.data_root,
            Importer(todo, OWNER),
            Waiter(wait, time.time, time.sleep),
        )
    failed = 0
    for result in results:
        if result.outcome is Outcome.FAILED:
            failed += 1
            LOG.error("failed %s: %s", result.bundle, result.detail)
        elif result.outcome is not Outcome.SKIPPED:
            LOG.info("%s %s %s", result.outcome, result.bundle, result.task_id or "")
    return 1 if failed else 0


def _sync(systemctl: Callable[[Sequence[str]], int]) -> int:
    paths = resolve_paths()
    try:
        changed = sync_units(paths.data_root, paths.unit_dir, systemctl)
    except RuntimeError:
        LOG.exception("sync failed")
        return 1
    LOG.info("watch list %s", "rewritten" if changed else "unchanged")
    return 0


def main(
    argv: Sequence[str] | None = None,
    *,
    client: TodoClient | None = None,
    systemctl: Callable[[Sequence[str]], int] = run_systemctl,
) -> int:
    """Entry point; ``client`` and ``systemctl`` are test seams."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _parser().parse_args(argv)
    if args.command == "run":
        return _run(args.wait, client)
    return _sync(systemctl)
