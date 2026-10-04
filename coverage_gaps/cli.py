"""Command line: `coverage-gaps REPORT [--json] [--max-files N] ...`."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from coverage_gaps.models import ReportError
from coverage_gaps.parsers import load_report
from coverage_gaps.render import select, to_json, to_markdown

EXIT_COVERED = 0
EXIT_GAPS = 1
EXIT_UNREADABLE = 2


def build_parser() -> argparse.ArgumentParser:
    """Argument parser (format is auto-detected from file content)."""
    parser = argparse.ArgumentParser(
        prog="coverage-gaps",
        description="List uncovered lines/branches from lcov, Cobertura, JaCoCo "
        "or coverage.py JSON reports. Exit 0 covered, 1 gaps, 2 unreadable.",
    )
    parser.add_argument("report", type=Path, help="coverage report file")
    parser.add_argument("--json", action="store_true", help="emit JSON, not markdown")
    parser.add_argument(
        "--max-files",
        type=int,
        default=0,
        metavar="N",
        help="list only the N worst files (0 = all)",
    )
    parser.add_argument(
        "--min-missed",
        type=int,
        default=1,
        metavar="N",
        help="skip files with fewer than N missed lines+branches",
    )
    parser.add_argument(
        "--path-prefix",
        default="",
        metavar="PREFIX",
        help="only files whose path starts with PREFIX",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the tool and return the process exit code."""
    args = build_parser().parse_args(argv)
    try:
        fmt, gaps = load_report(args.report)
    except ReportError as exc:
        print(f"coverage-gaps: {exc}", file=sys.stderr)
        return EXIT_UNREADABLE
    files = select(gaps, path_prefix=args.path_prefix, min_missed=args.min_missed)
    shown = args.max_files if args.max_files > 0 else len(files)
    render = to_json if args.json else to_markdown
    sys.stdout.write(render(fmt, files, shown) + ("\n" if args.json else ""))
    return EXIT_GAPS if files else EXIT_COVERED
