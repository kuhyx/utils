#!/usr/bin/env python3
"""AgentReady compliance checker (agentready.org spec v2.0).

    check.py dist <build-dir> [--act]   # pre-commit / CI: build output
    check.py url <base-url> [--act]     # post-deploy: the live site

Prints ``PASS|FAIL|SKIP AR-XXX-NN <msg>`` per check. Exit 0 all pass, 1 any
FAIL (every in-scope item is required, whatever its MUST/SHOULD/MAY
strength), 2 usage error, 3 network undeterminable.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit

if __package__ in (None, ""):  # run as a plain script: make the package importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_ready import checks_find, checks_read
from agent_ready.backends import DirSite, HttpSite, Site
from agent_ready.checks_act import run_act
from agent_ready.context import HOME, Ctx
from agent_ready.report import (
    EXIT_NETWORK,
    EXIT_USAGE,
    Report,
    Undeterminable,
)

# (AR id used when a network failure aborts the check, check function)
CHECKS: list[tuple[str, Callable[[Ctx], None]]] = [
    ("AR-FIND-01", checks_find.check_robots),
    ("AR-FIND-01", checks_find.check_agent_access),
    ("AR-FIND-03", checks_find.check_sitemap),
    ("AR-FIND-04", checks_find.check_catalog),
    ("AR-READ-01", checks_read.check_pages),
    ("AR-READ-02", checks_read.check_status_codes),
    ("AR-READ-03", checks_read.check_homepage),
    ("AR-READ-06", checks_read.check_discovery_links),
    ("AR-READ-07", checks_read.check_llms),
    ("AR-FIND-02", checks_read.skip_manual),
    ("AR-ACT-10", run_act),
]


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse the command line (argparse exits 2 on usage errors)."""
    parser = argparse.ArgumentParser(
        prog="agent_ready", description=__doc__.split("\n\n")[0]
    )
    sub = parser.add_subparsers(dest="mode", required=True)
    for mode, target in (
        ("dist", "build output directory"),
        ("url", "base URL, e.g. https://example.org"),
    ):
        cmd = sub.add_parser(mode, help=f"check a {target}")
        cmd.add_argument("target", help=target)
        cmd.add_argument(
            "--act",
            action="store_true",
            help="also check the act stage (OpenAPI, MCP, auth)",
        )
        cmd.add_argument(
            "--min-text",
            type=int,
            default=100,
            help="min visible chars per page (default 100)",
        )
        cmd.add_argument(
            "--max-pages",
            type=int,
            default=40,
            help="url mode: max pages to fetch (default 40; dist checks all)",
        )
    url = sub.choices["url"]
    url.add_argument(
        "--timeout",
        type=float,
        default=8.0,
        help="per-request timeout in s (default 8)",
    )
    url.add_argument(
        "--budget",
        type=float,
        default=45.0,
        help="overall network budget in s (default 45)",
    )
    return parser.parse_args(argv)


def make_site(args: argparse.Namespace) -> Site | None:
    """Build the backend, or report a usage error and return None."""
    if args.mode == "dist":
        root = Path(args.target)
        if not root.is_dir():
            print(f"agent_ready: not a directory: {root}", file=sys.stderr)
            return None
        return DirSite(root)
    parts = urlsplit(args.target)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        print(f"agent_ready: not an http(s) URL: {args.target}", file=sys.stderr)
        return None
    return HttpSite(args.target, timeout=args.timeout, budget=args.budget)


def main(argv: list[str] | None = None) -> int:
    """Run every check and return the exit code."""
    args = parse_args(argv)
    site = make_site(args)
    if site is None:
        return EXIT_USAGE
    report = Report(out=sys.stdout)
    ctx = Ctx(
        site=site,
        report=report,
        min_text=args.min_text,
        max_pages=args.max_pages,
        act=args.act,
    )
    try:
        site.get(HOME)
    except Undeterminable as exc:
        report.skip(
            "AR-FIND-01", f"undeterminable (network): homepage unreachable: {exc}"
        )
        return EXIT_NETWORK
    for ar_id, check in CHECKS:
        report.guard(ar_id, lambda check=check: check(ctx))
    return report.exit_code()


if __name__ == "__main__":
    sys.exit(main())
