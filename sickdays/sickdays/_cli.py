# Copyright (c) 2026 Krzysztof Rudnicki
"""The ``sickdays`` command: mark, un-mark and list sick days.

Every day is a normal day until marked here (or on the phone). There is no
budget and no reason to give; the one rule is the calendar -- today or later
only -- plus the cross-pool check: a free day cannot also be a sick day.

``sync-quiet`` is what the timer runs: it reports success even with no
network, because a unit that goes red whenever the laptop is offline is a
unit you learn to ignore.
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

from sickdays._api import add_sick_day, is_sick_day, remove_sick_day, sick_days
from sickdays._cli_output import emit, emit_error
from sickdays._day import resolve, to_iso, today
from sickdays._errors import SickDayError
from sickdays._sync import SyncUnavailableError, sync, sync_quietly

if TYPE_CHECKING:
    from collections.abc import Sequence

_EXIT_OK = 0
_EXIT_REFUSED = 1
_EXIT_BAD_INPUT = 2
_DAY_HELP = "YYYY-MM-DD, or 'today'/'tomorrow' (default: today)"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sickdays",
        description=(
            "One shared pool of sick days every gate respects. No cap, no "
            "reason; today or later only."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add", help="mark a day sick (today or later)")
    add.add_argument("day", nargs="?", default="today", help=_DAY_HELP)
    remove = sub.add_parser("remove", help="make a day normal again")
    remove.add_argument("day", nargs="?", default="today", help=_DAY_HELP)
    sub.add_parser("list", help="every sick day, oldest first")
    check = sub.add_parser(
        "check", help="exit 0 if the day is sick, 1 if not (for scripts)"
    )
    check.add_argument("day", nargs="?", default="today", help=_DAY_HELP)
    sub.add_parser("sync", help="pull and push the pool now")
    sub.add_parser(
        "sync-quiet",
        help="sync, but exit 0 when the network or credential is unavailable",
    )
    return parser


def _do_add(raw_day: str) -> int:
    entry = add_sick_day(resolve(raw_day))
    emit(f"{to_iso(entry.day)} is now a sick day")
    return _EXIT_OK


def _do_remove(raw_day: str) -> int:
    entry = remove_sick_day(resolve(raw_day))
    emit(f"{to_iso(entry.day)} is a normal day again")
    return _EXIT_OK


def _do_list() -> int:
    days = sorted(sick_days())
    if not days:
        emit("no sick days")
        return _EXIT_OK
    reference = today()
    for day in days:
        emit(f"{to_iso(day)}{'  (today)' if day == reference else ''}")
    return _EXIT_OK


def _do_check(raw_day: str) -> int:
    day = resolve(raw_day)
    sick = is_sick_day(day)
    emit(f"{to_iso(day)}: {'sick day' if sick else 'normal day'}")
    return _EXIT_OK if sick else _EXIT_REFUSED


def _do_sync() -> int:
    sync()
    emit("pool synced")
    return _EXIT_OK


def _do_sync_quiet() -> int:
    emit("pool synced" if sync_quietly() else "pool not synced (no remote available)")
    return _EXIT_OK


def _dispatch(args: argparse.Namespace) -> int:
    if args.command == "add":
        return _do_add(args.day)
    if args.command == "remove":
        return _do_remove(args.day)
    if args.command == "list":
        return _do_list()
    if args.command == "check":
        return _do_check(args.day)
    if args.command == "sync":
        return _do_sync()
    return _do_sync_quiet()


def main(argv: Sequence[str] | None = None) -> int:
    """Parse ``argv`` and run one subcommand.

    Returns:
        ``0`` on success, ``1`` for a refused or negative answer, ``2`` for
        input that could not be understood.
    """
    args = _build_parser().parse_args(argv)
    try:
        return _dispatch(args)
    except ValueError as exc:
        emit_error(f"error: {exc}")
        return _EXIT_BAD_INPUT
    except (SickDayError, SyncUnavailableError) as exc:
        emit_error(f"error: {exc}")
        return _EXIT_REFUSED


if __name__ == "__main__":
    sys.exit(main())
