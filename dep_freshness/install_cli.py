"""Command line for `install`: which repo, check-only, and the SDK pin."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dep_freshness.install import install, plan, write_fvmrc
from dep_freshness.registries.toolchain import flutter_latest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install the dependency-freshness gate into a repo."
    )
    parser.add_argument("repo", type=Path)
    parser.add_argument(
        "--check",
        action="store_true",
        help="report what would be written, change nothing",
    )
    parser.add_argument(
        "--fvm", action="store_true", help="also pin the Flutter SDK in <repo>/.fvmrc"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo = args.repo.resolve()

    if args.check:
        todo = plan(repo)
        for piece in todo:
            print(f"would write: {piece}")
        if not todo:
            print("gate already current")
        return 0

    for piece in install(repo):
        print(f"wrote: {piece}")

    if args.fvm:
        version, _dart = flutter_latest()
        if version is None:
            # Guessing a version here would pin every repo to a number nobody
            # chose, and the gate would then compare against it forever.
            print(
                "could not resolve latest stable Flutter; .fvmrc left alone",
                file=sys.stderr,
            )
            return 1
        if write_fvmrc(repo, version):
            print(f"wrote: .fvmrc (flutter {version})")

    return 0
