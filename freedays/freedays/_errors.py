"""Why a mark or un-mark was refused.

Each of these is a *policy* refusal with a message meant to be shown to the
person who typed the command. None of them indicates a bug, so callers are
expected to catch them and print ``str(exc)`` rather than let a traceback
out.
"""

from __future__ import annotations


class FreeDayError(Exception):
    """Base class for every policy refusal in this package."""


class PastDateError(FreeDayError):
    """A day in the past cannot be marked free.

    This is the one real abuse vector in an otherwise frictionless system:
    without it, a gate that already fired and was already failed could be
    erased after the fact.
    """


class BudgetExhaustedError(FreeDayError):
    """This calendar year has no free days left."""


class AlreadyFreeError(FreeDayError):
    """The day is already marked free, so marking it again would be a no-op."""


class NotFreeError(FreeDayError):
    """The day is not marked free, so there is nothing to release."""
