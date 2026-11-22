"""The commands `/leetcode review` and the skeleton sheets run (DOCS-review.md).

  python3 -m leetcode_coach.review_cli review-list
  python3 -m leetcode_coach.review_cli review-finish <slug> --cause <cause>
      [--module <unit>]      (--module with missing-idea, and only with it)
  python3 -m leetcode_coach.review_cli skeleton-open <slug> <unit>

A Claude Code session has no REPL and so no exported session log
(`session_log.append_current` writes nothing there): these commands are its
explicit write path. ``review-finish`` is the only writer of a ``review``
event and of the review ledger, and it refuses a slug the guard does not flag
right now. It signs the ledger row first and logs the event second: a failure
at either step leaves the slug flagged, so the same command can run again. An
abandoned review calls nothing and so writes nothing.

``skeleton-open`` prints the sheet file byte for byte on stdout and nothing
else there (the stop gate passes a sheet only when the reply quotes it
verbatim); its one confirmation line goes to stderr.

The printed lines are the interface (T201 exemption in pyproject.toml); the
tests assert on stdout.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import re
import sys
from typing import Final

from leetcode_coach import fetch_problem, flagged, progress, review_ledger, session_log

_LOG: Final = logging.getLogger(__name__)

SKELETON_DIR: Final = Path(__file__).with_name("skeletons")
SHEET_NAME: Final = "DOCS-{unit}.md"
CAUSES: Final = (
    "statement",
    "missing-idea",
    "idea-to-code",
    "debugging",
    "interruption",
)
MODULE_CAUSE: Final = "missing-idea"
CARD_CAUSES: Final = frozenset({"missing-idea", "idea-to-code"})
NOTHING: Final = "nothing to review"
EXIT_OK: Final = 0
EXIT_REFUSED: Final = 1
EXIT_UNCHECKED: Final = 2
EXIT_NOT_WRITTEN: Final = 3
_UNIT: Final = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def _refuse(why: str) -> int:
    print(f"refused: {why}")
    return EXIT_REFUSED


def _unchecked(exc: flagged.CouldNotCheckError, tail: str = "") -> int:
    print(f"could not check: {exc}{tail}")
    return EXIT_UNCHECKED


def review_list() -> int:
    """Print every flagged solve with its evidence, or `NOTHING`."""
    try:
        rows = flagged.flagged_rows()
    except flagged.CouldNotCheckError as exc:
        _LOG.warning("review-list could not read the flagged report: %s", exc)
        return _unchecked(exc)
    for row in rows:
        print(flagged.evidence_line(row))
    if not rows:
        print(NOTHING)
    return EXIT_OK


def _module_problem(cause: str, module: str | None) -> str | None:
    if (cause == MODULE_CAUSE) != (module is not None):
        return (
            f"--module names the unit for --cause {MODULE_CAUSE} and goes with "
            "no other cause; nothing written"
        )
    if module is not None and not _UNIT.fullmatch(module):
        return f"{module!r} is not a unit id; nothing written"
    return None


def review_finish(problem: str, cause: str, module: str | None) -> int:
    """Close one review: the signed ledger row, then the ``review`` event."""
    if (problem_text := _module_problem(cause, module)) is not None:
        return _refuse(problem_text)
    try:
        slug = fetch_problem.slug_from(problem)
        reviewable = flagged.flagged_slugs()
    except ValueError as exc:
        _LOG.warning("review-finish got a bad problem name: %s", exc)
        return _refuse(f"{exc}; nothing written")
    except flagged.CouldNotCheckError as exc:
        _LOG.warning("review-finish could not read the flagged report: %s", exc)
        return _unchecked(exc, "; nothing written")
    if slug not in reviewable:
        return _refuse(f"{slug} is not flagged, {NOTHING}; nothing written")
    return _record(slug, cause, module, due=len(reviewable))


def _record(slug: str, cause: str, module: str | None, *, due: int) -> int:
    """Write the rows, then the event, and say which of the two happened."""
    try:
        fresh = review_ledger.record(slug, cause, due=due)
    except review_ledger.LedgerError as exc:
        _LOG.warning("review of %s not recorded: %s", slug, exc)
        print(
            f"nothing written: no signed ledger row ({exc}), so no review event "
            "either; fix that and run the same command again"
        )
        return EXIT_NOT_WRITTEN
    fields = {"cause": cause} if module is None else {"cause": cause, "module": module}
    try:
        session_log.append(session_log.log_path(slug), "review", **fields)
    except OSError as exc:
        _LOG.warning("review event for %s not logged: %s", slug, exc)
        print(
            f"ledger row written, review event NOT logged ({exc}); "
            "run the same command again"
        )
        return EXIT_NOT_WRITTEN
    named = f", module {module}" if module is not None else ""
    print(f"review logged: {slug}, cause {cause}{named}")
    print("ledger row: " + ("written" if fresh else "already there, not written twice"))
    if cause in CARD_CAUSES:
        print("card: build ONE property -> operation card now (DOCS-review.md step 6)")
    else:
        print("card: none for this cause")
    return EXIT_OK


def skeleton_open(problem: str, unit: str) -> int:
    """Log a ``skeleton`` event and print the unit's sheet, after a code attempt.

    A ``code`` event in any of the slug's session logs counts; so does a slug
    the guard flags right now (a review: the accepted submission is the code).
    """
    try:
        slug = fetch_problem.slug_from(problem)
    except ValueError as exc:
        _LOG.warning("skeleton-open got a bad problem name: %s", exc)
        return _refuse(f"{exc}; nothing logged")
    if not _UNIT.fullmatch(unit):
        return _refuse(f"{unit!r} is not a unit id; nothing logged")
    sheet = SKELETON_DIR / SHEET_NAME.format(unit=unit)
    if not sheet.is_file():
        return _refuse(
            f"no skeleton sheet for unit {unit!r} at {sheet}; nothing logged"
        )
    if progress.count_events(slug, "code") == 0:
        try:
            in_review = slug in flagged.flagged_slugs()
        except flagged.CouldNotCheckError as exc:
            _LOG.warning("skeleton-open could not read the flagged report: %s", exc)
            return _unchecked(exc, "; no code attempt in the log, nothing logged")
        if not in_review:
            return _refuse(
                f"{slug} has no code attempt yet (no code event, not flagged): "
                "a skeleton opens only after the first code; nothing logged"
            )
    text = sheet.read_bytes()
    session_log.append(session_log.log_path(slug), "skeleton", unit=unit)
    sys.stdout.flush()
    sys.stdout.buffer.write(text)
    sys.stdout.buffer.flush()
    print(f"skeleton logged: {slug}, unit {unit}", file=sys.stderr)
    return EXIT_OK


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="review_cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("review-list", help="flagged solves with their evidence")
    finish = sub.add_parser("review-finish", help="close a review with its one cause")
    finish.add_argument("slug")
    finish.add_argument("--cause", choices=CAUSES, required=True)
    finish.add_argument("--module", help=f"unit id; only with {MODULE_CAUSE}")
    opener = sub.add_parser("skeleton-open", help="log and print a unit's sheet")
    opener.add_argument("slug")
    opener.add_argument("unit")
    return parser


def main(argv: list[str]) -> int:
    """Dispatch one of the three commands; 0 only when it did its job."""
    args = _parser().parse_args(argv)
    if args.command == "review-list":
        return review_list()
    if args.command == "review-finish":
        return review_finish(args.slug, args.cause, args.module)
    return skeleton_open(args.slug, args.unit)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
