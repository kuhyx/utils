# Copyright (c) 2026 Krzysztof Rudnicki
"""Session recording CLI; a game's own entry script calls `main(argv, config)`.

wrap [--session ID] [--force] [--audio SRC] [--fps N] [--max-seconds S] -- <game command>
finalize <rec.json>             rebuild events.json + chapters
latest|list [--dir D]           moments of the newest recording / all recordings
open [N] [--session ID] [--dir D] [--dry-run]
"""

import argparse
import os
from pathlib import Path
import sys
from typing import TYPE_CHECKING

from game_recording import finalize, library, supervise
from game_recording.options import DEFAULT_FPS, RunOptions

if TYPE_CHECKING:
    from collections.abc import Sequence

    from game_recording.config import Config
    from game_recording.library import Doc


def default_dir(config: Config) -> Path:
    """The recordings folder of the game's default feedback dir."""
    return supervise.feedback_dir([], os.environ, config) / "recordings"


def pick(rec_dir: Path, session: str) -> Doc:
    """The newest recording (of the session whose id starts with `session`, when given)."""
    found = library.sessions(rec_dir)
    if session:
        found = [p for p in found if p.name.startswith(session)]
    if not found:
        msg = f"no recordings in {rec_dir}"
        raise SystemExit(msg)
    return library.load(found[0])


def parser() -> argparse.ArgumentParser:
    """The argument parser of every subcommand."""
    top = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = top.add_subparsers(dest="cmd", required=True)
    wrap = sub.add_parser("wrap")
    wrap.add_argument("--session", default="")
    wrap.add_argument("--force", action="store_true", help="record bot/test runs too (tests only)")
    wrap.add_argument("--audio", default="default", help="default|lavfi|<pulse source>")
    wrap.add_argument("--fps", type=int, default=DEFAULT_FPS)
    wrap.add_argument("--max-seconds", type=float, default=0.0)
    wrap.add_argument("command", nargs=argparse.REMAINDER)
    fin = sub.add_parser("finalize")
    fin.add_argument("meta")
    for name in ("latest", "list", "open"):
        p = sub.add_parser(name)
        p.add_argument("--dir", default="")
        p.add_argument("--session", default="")
        if name == "open":
            p.add_argument("n", nargs="?", type=int)
            p.add_argument("--dry-run", action="store_true")
    return top


def _wrap(args: argparse.Namespace, config: Config) -> int:
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    options = RunOptions(
        force=args.force, session=args.session, audio=args.audio, fps=args.fps, max_seconds=args.max_seconds
    )
    return supervise.run(command, config, options)


def _show(args: argparse.Namespace, config: Config) -> int:
    rec_dir = Path(args.dir) if args.dir else default_dir(config)
    if args.cmd == "list":
        sys.stdout.write(library.listing(rec_dir) + "\n")
    elif args.cmd == "latest":
        sys.stdout.write(library.table(pick(rec_dir, args.session)) + "\n")
    else:
        try:
            return library.open_moment(pick(rec_dir, args.session), rec_dir, args.n, dry_run=args.dry_run)
        except IndexError as err:
            raise SystemExit(str(err)) from err
    return 0


def main(argv: Sequence[str], config: Config) -> int:
    """Runs one subcommand for the game described by `config`; returns the exit code."""
    args = parser().parse_args(argv)
    if args.cmd == "wrap":
        return _wrap(args, config)
    if args.cmd == "finalize":
        finalize.finalize(Path(args.meta), config.moments)
        return 0
    return _show(args, config)
