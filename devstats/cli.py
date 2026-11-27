"""`python -m devstats compare [--root DIR]... [--email ADDR]... [--by-repo [N]] [--write]`."""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import TextIO

from devstats import article as A
from devstats.aggregate import DAY, RepoData, Window, dedup, window_totals
from devstats.discover import Repo, discover
from devstats.numstat import read_commits
from devstats.refs import list_refs, resolve, tag_times
from devstats.render import by_repo, document, report

DEFAULT_EMAIL = "krzysztofrudnicki0@gmail.com"
DOC_PATH = Path(__file__).resolve().parent / "DOCS-comparison.md"
EXIT_NO_REPOS = 2


def build_parser() -> argparse.ArgumentParser:
    """Argument parser with the single `compare` subcommand."""
    parser = argparse.ArgumentParser(prog="devstats", description="kuhy's git output vs the 100x article")
    sub = parser.add_subparsers(dest="cmd", required=True)
    cmp = sub.add_parser("compare", help="print kuhy's 30/90/300-day numbers beside the article's")
    cmp.add_argument("--root", action="append", type=Path, default=[],
                     help="directory whose child repos are walked (repeatable; default ~/src)")
    cmp.add_argument("--email", action="append", default=[],
                     help=f"extra author email to count (repeatable; {DEFAULT_EMAIL} always counts)")
    cmp.add_argument("--by-repo", nargs="?", type=int, const=10, default=0, metavar="N",
                     help="also print the top N repos (terminal only, default N=10)")
    cmp.add_argument("--write", action="store_true", help="rewrite devstats/DOCS-comparison.md")
    return parser


def _collect(repo: Repo, emails: frozenset[str], since: int) -> tuple[RepoData, list[str]]:
    """Commits by `emails` on the repo's default branch since `since`, its tags, warnings."""
    refs = list_refs(repo.path)
    default = resolve(refs)
    tags = tuple(tag_times(refs))
    if default.branch is None:
        return RepoData(repo.name, (), tags), [f"{repo.name}: no main/master/origin HEAD branch, skipped"]
    warnings = []
    if default.behind_days is not None:
        warnings.append(f"{repo.name} ({default.branch}): default ref is {default.behind_days} days "
                        "behind its upstream tracking ref")
    commits = tuple(c for c in read_commits(repo.path, default.log_refs, since) if c.email in emails)
    return RepoData(repo.name, commits, tags), warnings


def main(argv: Sequence[str] | None = None, *, now: float | None = None, out: TextIO = sys.stdout,
         err: TextIO = sys.stderr, doc_path: Path = DOC_PATH) -> int:
    """Run the CLI; returns the exit code (2 when no repo was found)."""
    args = build_parser().parse_args(argv)
    now = time.time() if now is None else now
    roots = args.root or [Path.home() / "src"]
    emails = frozenset(e.lower() for e in (DEFAULT_EMAIL, *args.email))
    repos, warnings = discover(roots)
    if not repos:
        print(f"devstats: no git repos under {', '.join(map(str, roots))}", file=err)
        return EXIT_NO_REPOS
    since = int(now - max(A.WINDOWS) * DAY)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda r: _collect(r, emails, since), repos))
    data = dedup([d for d, _ in results])
    for w in (*warnings, *(w for _, ws in results for w in ws)):
        print(f"warning: {w}", file=err)
    windows: list[Window] = [window_totals(data, d, now) for d in A.WINDOWS]
    print(report(windows), file=out)
    if args.by_repo:
        per_repo = [(d.name, [window_totals([d], days, now) for days in A.WINDOWS]) for d in data]
        print(by_repo(per_repo, args.by_repo), file=out)
    if args.write:
        doc_path.write_text(document(windows, datetime.fromtimestamp(now).date().isoformat()))
        print(f"wrote {doc_path}", file=out)
    return 0
