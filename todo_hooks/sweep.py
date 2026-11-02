"""Drift sweep: which open notes already have a passing, trusted done_check."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field, replace
import os
from pathlib import Path
import tempfile
from typing import TYPE_CHECKING

from todo_hooks.checkrun import CHECK_TIMEOUT, run_check
from todo_hooks.client import McpError, McpToolError
from todo_hooks.context import describe
from todo_hooks.gitrepo import expected_repo
from todo_hooks.notes import Task, parse_detail, parse_list
from todo_hooks.trust import is_trusted

if TYPE_CHECKING:
    from collections.abc import Callable

    from todo_hooks.checkrun import CheckResult
    from todo_hooks.context import Context


USAGE = (
    "usage: python3 -m todo_hooks sweep [--dry-run] [--report PATH] [--trust-file PATH]"
)


@dataclass
class Tally:
    """Per-outcome counts plus the report rows they produced."""

    total: int = 0
    counts: dict[str, int] = field(default_factory=dict)
    passing: list[str] = field(default_factory=list)
    manual: list[str] = field(default_factory=list)

    def record(self, outcome: str, label: str) -> None:
        self.counts[outcome] = self.counts.get(outcome, 0) + 1
        if outcome == "pass":
            self.passing.append(label)
        elif outcome == "manual":
            self.manual.append(label)

    def lines(self, *, dry_run: bool) -> list[str]:
        head = "would-run " if dry_run else ""
        rows = [head + row for row in self.passing]
        rows += [f"# close by hand: {row}" for row in self.manual]
        get = self.counts.get
        tail = f"{get('untrusted', 0)} untrusted, {get('manual', 0)} manual"
        tail += f", {get('nolocal', 0)} no local repo"
        if dry_run:
            summary = (
                f"# dry-run: {self.total} open notes: "
                f"{get('pass', 0)} would run, {tail}"
            )
        else:
            summary = (
                f"# swept {self.total} open notes: {get('pass', 0)} pass, "
                f"{get('fail', 0)} fail, {get('timeout', 0)} timeout, {tail}"
            )
        return [*rows, summary]


def local_repos(src_root: Path) -> dict[str, Path]:
    """Map ``kuhyx/<origin name>`` to each git checkout directly under src_root."""
    if not src_root.is_dir():
        return {}
    return {
        expected_repo(child): child
        for child in sorted(src_root.iterdir())
        if (child / ".git").exists()
    }


def _write_report(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".report-")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    Path(tmp).replace(path)


def run(
    ctx: Context,
    *,
    dry_run: bool = False,
    report: Path | None = None,
    runner: Callable[..., CheckResult] = run_check,
) -> int:
    """Sweep every open repo note; 1 when the server cannot be reached."""
    repos = local_repos(ctx.paths.src_root)
    tally = Tally()
    try:
        client = ctx.make_client()
        try:
            rows = parse_list(client.call("list_tasks", {"status": "open"}))
            tally.total = len(rows)
            for row in rows:
                root = repos.get(row.repo)
                if root is None:
                    tally.record("nolocal", row.id8)
                    continue
                try:
                    task = parse_detail(client.call("get_task", {"id": row.id8}))
                except McpToolError:
                    continue
                outcome = _outcome(ctx, task, root, runner, dry_run=dry_run)
                label = f"{row.id8} {row.repo} {row.title}"
                tally.record(outcome, label)
        finally:
            client.close()
    except McpError as err:
        ctx.say(f"sweep failed: {describe(err)}")
        return 1
    lines = tally.lines(dry_run=dry_run)
    _write_report(report or ctx.paths.report_file, lines)
    for line in lines:
        ctx.out(line)
    return 0


def _outcome(
    ctx: Context,
    task: Task,
    root: Path,
    runner: Callable[..., CheckResult],
    *,
    dry_run: bool,
) -> str:
    check = task.done_check
    if task.status == "done" or not check:
        return "skip"
    if task.is_manual:
        return "manual"
    if not is_trusted(ctx.paths.trust_file, check):
        return "untrusted"
    if dry_run:
        return "pass"
    result = runner(check, root, timeout=CHECK_TIMEOUT, wrapper=ctx.paths.capped)
    return "timeout" if result.timed_out else "pass" if result.passed else "fail"


def main(ctx: Context, args: list[str]) -> int:
    """Parse ``--dry-run``, ``--report PATH``, ``--trust-file PATH`` and run."""
    parser = argparse.ArgumentParser(prog="todo_hooks sweep", exit_on_error=False)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--trust-file", type=Path)
    try:
        opts = parser.parse_args(args)
    except argparse.ArgumentError, SystemExit:
        ctx.out(USAGE)
        return 2
    if opts.trust_file:
        ctx.paths = replace(ctx.paths, trust_file=opts.trust_file)
    return run(ctx, dry_run=opts.dry_run, report=opts.report)
