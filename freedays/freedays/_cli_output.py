"""The one stdout/stderr sink every ``freedays`` subcommand writes through.

A thin wrapper over ``sys.stdout.write`` (the shape diet-guard and home-guard
already use) so genuine CLI output does not trip ruff's ``T201`` without a
suppression. Kept deliberately trivial: ``T201`` is *auto-fixable*, and its
unsafe fix deletes the whole ``print`` call -- output and all.
"""

from __future__ import annotations

import sys


def emit(text: str = "") -> None:
    """Write one line to stdout."""
    sys.stdout.write(f"{text}\n")


def emit_error(text: str) -> None:
    """Write one line to stderr."""
    sys.stderr.write(f"{text}\n")
