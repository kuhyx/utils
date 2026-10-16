# Copyright (c) 2026 Krzysztof Rudnicki
"""The ``sickdays`` command: mark, un-mark and list sick days.

Every day is a normal day until marked here (or on the phone). There is no
budget and no reason to give; the one rule is the calendar -- today or later
only -- plus the cross-pool check: a free day cannot also be a sick day.

A sick day stands every locker down unless it *keeps* some (``--keep`` on
``add``, or ``keep`` afterwards). Locker ids are argparse ``choices``, so a
typo exits 2 instead of silently keeping nothing.

``sync-quiet`` is what the timer runs: it reports success even with no
network, because a unit that goes red whenever the laptop is offline is a
unit you learn to ignore.
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

from sickdays._api import add_sick_day, is_sick_day, load, remove_sick_day
from sickdays._cli_output import emit, emit_error
from sickdays._constants import LOCKERS
from sickdays._day import resolve, to_iso, today
from sickdays._errors import SickDayError
from sickdays._keep_api import set_kept_lockers, stands_down
from sickdays._model import sick_entries
from sickdays._sync import SyncUnavailableError, sync, sync_quietly

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

_EXIT_OK = 0
_EXIT_REFUSED = 1
_EXIT_BAD_INPUT = 2
_DAY_HELP = "YYYY-MM-DD, or 'today'/'tomorrow' (default: today)"
_LOCKER_METAVAR = "LOCKER"


def _keep_suffix(keep: frozenset[str]) -> str:
    """``"  keep: a, b"`` for a non-empty keep set, else nothing."""
    return f"  keep: {', '.join(sorted(keep))}" if keep else ""


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
    add.add_argument(
        "--keep",
        action="append",
        default=[],
        choices=LOCKERS,
        metavar=_LOCKER_METAVAR,
        help=f"keep this locker active (repeatable; one of {', '.join(LOCKERS)})",
    )
    keep = sub.add_parser(
        "keep", help="replace the lockers an existing sick day keeps active"
    )
    keep.add_argument("day", help="YYYY-MM-DD, or 'today'/'tomorrow'")
    keep.add_argument(
        "lockers",
        nargs="*",
        choices=LOCKERS,
        metavar=_LOCKER_METAVAR,
        help="lockers to keep; none stands every locker down again",
    )
    remove = sub.add_parser("remove", help="make a day normal again")
    remove.add_argument("day", nargs="?", default="today", help=_DAY_HELP)
    sub.add_parser("list", help="every sick day, oldest first")
    check = sub.add_parser(
        "check",
        help=(
            "exit 0 if the day is sick (with --locker: if that locker stands "
            "down), 1 if not -- for scripts"
        ),
    )
    check.add_argument("day", nargs="?", default="today", help=_DAY_HELP)
    check.add_argument(
        "--locker",
        choices=LOCKERS,
        metavar=_LOCKER_METAVAR,
        help="instead: exit 0 iff this locker stands down on the day, 1 if not",
    )
    sub.add_parser("sync", help="pull and push the pool now")
    sub.add_parser(
        "sync-quiet",
        help="sync, but exit 0 when the network or credential is unavailable",
    )
    return parser


def _do_add(raw_day: str, keep: list[str]) -> int:
    entry = add_sick_day(resolve(raw_day), keep=keep)
    emit(f"{to_iso(entry.day)} is now a sick day{_keep_suffix(entry.keep)}")
    return _EXIT_OK


def _do_keep(raw_day: str, lockers: list[str]) -> int:
    entry = set_kept_lockers(resolve(raw_day), lockers)
    if entry.keep:
        emit(f"{to_iso(entry.day)}{_keep_suffix(entry.keep)}")
    else:
        emit(f"{to_iso(entry.day)}: every locker stands down")
    return _EXIT_OK


def _do_remove(raw_day: str) -> int:
    entry = remove_sick_day(resolve(raw_day))
    emit(f"{to_iso(entry.day)} is a normal day again")
    return _EXIT_OK


def _do_list() -> int:
    entries = sick_entries(load())
    if not entries:
        emit("no sick days")
        return _EXIT_OK
    reference = today()
    for entry in entries:
        marker = "  (today)" if entry.day == reference else ""
        emit(f"{to_iso(entry.day)}{marker}{_keep_suffix(entry.keep)}")
    return _EXIT_OK


def _do_check(raw_day: str, locker: str | None) -> int:
    day = resolve(raw_day)
    if locker is not None:
        off = stands_down(locker, day)
        emit(f"{to_iso(day)}: {locker} {'stands down' if off else 'applies'}")
        return _EXIT_OK if off else _EXIT_REFUSED
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


_HANDLERS: dict[str, Callable[[argparse.Namespace], int]] = {
    "add": lambda args: _do_add(args.day, args.keep),
    "keep": lambda args: _do_keep(args.day, args.lockers),
    "remove": lambda args: _do_remove(args.day),
    "list": lambda _args: _do_list(),
    "check": lambda args: _do_check(args.day, args.locker),
    "sync": lambda _args: _do_sync(),
    "sync-quiet": lambda _args: _do_sync_quiet(),
}


def main(argv: Sequence[str] | None = None) -> int:
    """Parse ``argv`` and run one subcommand.

    Returns:
        ``0`` on success, ``1`` for a refused or negative answer, ``2`` for
        input that could not be understood.
    """
    args = _build_parser().parse_args(argv)
    try:
        return _HANDLERS[args.command](args)
    except ValueError as exc:
        emit_error(f"error: {exc}")
        return _EXIT_BAD_INPUT
    except (SickDayError, SyncUnavailableError) as exc:
        emit_error(f"error: {exc}")
        return _EXIT_REFUSED


if __name__ == "__main__":
    sys.exit(main())
