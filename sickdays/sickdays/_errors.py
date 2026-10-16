# Copyright (c) 2026 Krzysztof Rudnicki
"""Why an add, a remove or a free-day mark was refused.

Each of these is a *policy* refusal with a message meant to be shown to the
person who typed the command. None of them indicates a bug, so callers are
expected to catch :class:`SickDayError` and print ``str(exc)`` rather than
let a traceback out.
"""

from __future__ import annotations


class SickDayError(Exception):
    """Base class for every policy refusal in this package."""


class PastDateError(SickDayError):
    """A past day can be neither added nor removed.

    Without this a gate that already fired and was already failed could be
    erased after the fact -- or a day that was rightly excused could be
    un-excused retroactively. Only :func:`sickdays.import_legacy` writes past
    dates, once, from screen-locker's old history.
    """


class AlreadySickError(SickDayError):
    """The day is already a sick day, so adding it again would be a no-op."""


class NotSickError(SickDayError):
    """The day is not a sick day, so there is nothing to remove."""


class FreeDayConflictError(SickDayError):
    """The day is a free day; a date cannot be in both pools."""


class SickDayConflictError(SickDayError):
    """The day is a sick day, so it cannot also be marked free."""


class ConflictCheckUnavailableError(SickDayError):
    """The free-day pool could not be consulted, so the add is refused.

    "A date is never in both pools" is a hard invariant, so not being able
    to check it is a refusal, not a pass.
    """


class UnreadablePoolError(SickDayError):
    """The local pool file exists but cannot be read or parsed.

    Readers treat that as "no sick days" (fail closed: the gates apply).
    Writers refuse instead: rewriting the file from an empty pool would
    silently destroy every entry the unreadable file still holds.
    """
