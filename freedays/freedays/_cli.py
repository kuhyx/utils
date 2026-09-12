# Copyright (c) 2026 Krzysztof Rudnicki
"""The ``freedays`` command: the only thing that ever talks about free days.

Every subcommand that says anything is pull, never push: nothing notifies,
and no gate ever invokes this to nag -- the apps consult
:func:`freedays.is_free_day` silently and say nothing either way. If you
want to know where the pool stands, you ask; otherwise it is invisible.

``sync-quiet`` is the one subcommand a timer runs, and it exists precisely
so that the timer stays silent: it moves data between devices and reports
success even when there is no network, because a unit that goes red every
time the laptop is offline is a unit you learn to ignore.
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

from freedays._api import is_free_day as _is_free_day
from freedays._api import mark, release, status
from freedays._cli_output import emit, emit_error
from freedays._constants import DEFAULT_ANNUAL_BUDGET
from freedays._day import resolve, to_iso
from freedays._errors import FreeDayError
from freedays._sync import SyncUnavailableError, sync, sync_quietly

if TYPE_CHECKING:
    from collections.abc import Sequence

_EXIT_OK = 0
_EXIT_REFUSED = 1
_EXIT_BAD_INPUT = 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="freedays",
        description=(
            "One shared pool of days on which every gate app stands down. "
            f"{DEFAULT_ANNUAL_BUDGET} per calendar year, resetting Jan 1."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    show = sub.add_parser("status", help="how many days are left this year")
    show.add_argument("--year", type=int, default=None)

    check = sub.add_parser(
        "check", help="exit 0 if the day is free, 1 if it is not (for scripts)"
    )
    check.add_argument("day", nargs="?", default="today")

    take = sub.add_parser("mark", help="take a day off, today or later")
    take.add_argument("day", help="YYYY-MM-DD, or 'today'/'tomorrow'")
    take.add_argument("--reason", default="", help="optional, never required")

    give = sub.add_parser("release", help="give a day back")
    give.add_argument("day", help="YYYY-MM-DD, or 'today'/'tomorrow'")

    sub.add_parser("sync", help="pull and push the pool now")
    sub.add_parser(
        "sync-quiet",
        help="sync, but exit 0 when the network or credential is unavailable",
    )
    return parser


def _show_status(year: int | None) -> int:
    current = status(year=year)
    emit(f"{current.year}: {current.left} of {current.budget} free days left")
    if current.today_is_free:
        emit("today is a free day -- every gate is standing down")
    if current.upcoming:
        upcoming = ", ".join(to_iso(day) for day in current.upcoming)
        emit(f"booked ahead: {upcoming}")
    return _EXIT_OK


def _do_check(raw_day: str) -> int:
    day = resolve(raw_day)
    free = _is_free_day(day)
    emit(f"{to_iso(day)}: {'free' if free else 'normal rules apply'}")
    return _EXIT_OK if free else _EXIT_REFUSED


def _do_mark(raw_day: str, reason: str) -> int:
    entry = mark(resolve(raw_day), reason=reason)
    left = status(year=entry.day.year).left
    emit(f"{to_iso(entry.day)} is now a free day ({left} left in {entry.day.year})")
    return _EXIT_OK


def _do_release(raw_day: str) -> int:
    entry = release(resolve(raw_day))
    left = status(year=entry.day.year).left
    refunded = (
        "not refunded (the day had already started)" if entry.consumed else "refunded"
    )
    emit(f"{to_iso(entry.day)} released, {refunded} -- {left} left in {entry.day.year}")
    return _EXIT_OK


def _do_sync() -> int:
    sync()
    emit("pool synced")
    return _EXIT_OK


def _do_sync_quiet() -> int:
    """Sync on a timer's behalf, treating unavailability as success.

    A systemd unit that goes red every time the laptop is offline trains you
    to ignore it, which is worse than not having it. A genuine bug still
    reaches the journal through the library's own logging.
    """
    emit("pool synced" if sync_quietly() else "pool not synced (no remote available)")
    return _EXIT_OK


def _dispatch(args: argparse.Namespace) -> int:
    if args.command == "status":
        return _show_status(args.year)
    if args.command == "check":
        return _do_check(args.day)
    if args.command == "mark":
        return _do_mark(args.day, args.reason)
    if args.command == "release":
        return _do_release(args.day)
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
    except (FreeDayError, SyncUnavailableError) as exc:
        emit_error(f"error: {exc}")
        return _EXIT_REFUSED


if __name__ == "__main__":
    sys.exit(main())
