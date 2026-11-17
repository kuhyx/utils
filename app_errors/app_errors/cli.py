# Copyright (c) 2026 Krzysztof Rudnicki
"""``app-errors``: ``ingest`` (what the timer runs) and ``resolve <app> <signature>``."""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from typing import TYPE_CHECKING

from app_errors import ingest, store
from app_errors.rtdb import DEFAULT_SESSION, RtdbError, open_rtdb

if TYPE_CHECKING:
    from collections.abc import Sequence


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="app-errors", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("ingest", help="read RTDB and the spool, write the board reports")
    run.add_argument("--keep", action="store_true", help="leave RTDB entries in place")
    run.add_argument("--no-rtdb", action="store_true", help="read the local spool only")
    run.add_argument("--session", default=DEFAULT_SESSION, help="seeded crdt-sync credential store")
    res = sub.add_parser("resolve", help="mark an error fixed (a newer build reopens it)")
    res.add_argument("app")
    res.add_argument("signature")
    return parser


def _ingest(args: argparse.Namespace) -> int:
    db, error = None, None
    if not args.no_rtdb:
        try:
            db = open_rtdb(args.session)
        except RtdbError as e:
            error = str(e)
    summary = ingest.run(ingest.default_paths(), db, keep=args.keep)
    error = error or summary.rtdb_error
    print(f"app-errors: {summary.merged} new")  # noqa: T201 -- terminal-only CLI
    if error:
        print(f"app-errors: RTDB: {error}", file=sys.stderr)  # noqa: T201
        return 1
    return 0


def _resolve(args: argparse.Namespace) -> int:
    paths = ingest.default_paths()
    state = store.load(paths.state)
    now = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    if not store.resolve(state, args.app, args.signature, now=now):
        print(f"app-errors: unknown error {args.app} {args.signature}", file=sys.stderr)  # noqa: T201
        return 1
    store.save(paths.state, state)
    store.write_reports(paths.reports, state)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI; return the exit code."""
    args = _parser().parse_args(argv)
    return _ingest(args) if args.command == "ingest" else _resolve(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
