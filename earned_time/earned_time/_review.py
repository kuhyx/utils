# Copyright (c) 2026 Krzysztof Rudnicki
"""The LeetCode review top-up (0.23.0): which coach review rows pay.

The coach (``/leetcode review``) signs one ``credit`` row per finished review
in its own ledger. A row pays only if it is signed, its ``detail.source`` is
:data:`REVIEW_SOURCE`, it finished in the day's window, it is the earliest
signed review of its ``detail.title_slug`` (each slug pays once, ever), and
the LeetCode guard's ledger holds a signed, non-manual accepted submission of
that slug from the :data:`ACCEPTED_LOOKBACK_DAYS` before the review finished.

The review row alone proves nothing (the coach's flag rests on unsigned
heartbeats), so the guard's accepted submission is the evidence and the
once-per-slug rule is the cap on forgery (kuhy, 2026-11-21, Q14).

**Fail closed, logged.** An unreadable guard ledger is ``None`` ("could not
check", one warning from :func:`~earned_time._ledger.read_rows`); a row with
no slug or no usable ``finished_at`` pays nothing, with a warning. No review
row in the window is an honest "no" and never reads the guard ledger.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
import logging
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Final

from earned_time._evidence import MANUAL_PREFIXES, MANUAL_SOURCES
from earned_time._ledger import read_rows, verified
from earned_time._policy import Earner

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from earned_time._policy import Window

    # (earner, ledger, key, rows, window) -> the rows that pay, or ``None``.
    RowEvidence = Callable[
        [Earner, Path, bytes, list[object], Window],
        Iterator[dict[str, object]] | None,
    ]

_logger: Final = logging.getLogger(__name__)

# The first day the review earner is in the registry: the day after the
# planned deploy (2026-11-22).
REVIEW_FROM: Final = date(2026, 11, 23)
# What the day's first paid review adds to shutdown, capped at the ceiling.
REVIEW_SHUTDOWN_MINUTES: Final = 20
REVIEW_SOURCE: Final = "leetcode-coach-review"
REVIEW_LEDGER: Final = ".local/share/leetcode-coach/review_ledger.json"
# The LeetCode guard's ledger (``LEETCODE.ledger``), relative to the home.
GUARD_LEDGER: Final = ".local/share/leetcode_guard/ledger.json"
GUARD_SOURCE: Final = "leetcode"
# How old the accepted submission may be when the review finishes.
ACCEPTED_LOOKBACK_DAYS: Final = 14
_LOOKBACK_SECONDS: Final = ACCEPTED_LOOKBACK_DAYS * 24 * 60 * 60


def _detail(row: dict[str, object]) -> dict[str, object]:
    detail = row.get("detail")
    return detail if isinstance(detail, dict) else {}


def _stamp(raw: object) -> float | None:
    """A unix-seconds stamp, or ``None`` when absent or unparsable."""
    try:
        return float(str(raw))
    except ValueError:
        return None


def review_match(row: dict[str, object], window: Window) -> bool:
    """A coach review row that finished in ``window``.

    Like ``leetcode_match``: ``finished_at`` decides, the row's ``day`` is the
    fallback for a row without a usable stamp (that row still pays nothing:
    the lookback needs the stamp, :func:`paid_reviews`).
    """
    detail = _detail(row)
    if detail.get("source") != REVIEW_SOURCE:
        return False
    stamp = _stamp(detail.get("finished_at"))
    if stamp is not None:
        return window[0] <= stamp <= window[1]
    local = datetime.fromtimestamp(window[0], tz=UTC).astimezone().date()
    return row.get("day") == local.isoformat()


def _slug(row: dict[str, object]) -> str | None:
    slug = _detail(row).get("title_slug")
    return slug if isinstance(slug, str) and slug else None


def _manual(row: dict[str, object]) -> bool:
    """A guard row a human granted: manual source, id, or ``manual_grant`` note."""
    detail = _detail(row)
    return (
        detail.get("source") in MANUAL_SOURCES
        or "manual_grant" in detail
        or str(row.get("entry_id")).startswith(MANUAL_PREFIXES)
    )


def _accepted(rows: list[object], key: bytes) -> dict[str, list[float]]:
    """Each slug's signed, non-manual accepted-submission stamps in the guard."""
    found: dict[str, list[float]] = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("kind") != "credit":
            continue
        if not verified(row, key) or _manual(row):
            continue
        detail = _detail(row)
        slug = _slug(row)
        stamp = _stamp(detail.get("submitted_at"))
        if detail.get("source") == GUARD_SOURCE and slug and stamp is not None:
            found.setdefault(slug, []).append(stamp)
    return found


def _order(row: dict[str, object]) -> float:
    """When a review happened, for "earliest": ``finished_at``, else ``created_at``."""
    stamp = _stamp(_detail(row).get("finished_at"))
    if stamp is not None:
        return stamp
    try:
        return datetime.fromisoformat(str(row.get("created_at"))).timestamp()
    except ValueError:
        return float("inf")


def _firsts(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    """The earliest signed review row of each slug (a tie: the first written)."""
    firsts: dict[str, dict[str, object]] = {}
    for row in sorted(rows, key=_order):
        slug = _slug(row)
        if slug is not None:
            firsts.setdefault(slug, row)
    return firsts


def guard_ledger_for(ledger: Path, earner: Earner) -> Path:
    """The guard ledger under the same home as ``ledger`` (``earner.ledger``).

    The consumer resolves only the review ledger (``home / earner.ledger``),
    so the home is that path with ``earner.ledger``'s depth stripped: a test
    that redirects the home redirects both ledgers.
    """
    depth = len(PurePosixPath(str(earner.ledger)).parts)
    return ledger.parents[depth - 1] / GUARD_LEDGER


def _pays(row: dict[str, object], accepted: dict[str, list[float]]) -> bool:
    """Whether a slug's first review is backed by an accepted submission."""
    finished = _stamp(_detail(row).get("finished_at"))
    if finished is None:
        _logger.warning(
            "LeetCode review %r has no usable finished_at; it pays nothing",
            row.get("entry_id"),
        )
        return False
    slug = str(_slug(row))
    return any(
        finished - _LOOKBACK_SECONDS <= t <= finished for t in accepted.get(slug, ())
    )


def paid_reviews(
    earner: Earner, ledger: Path, key: bytes, rows: list[object], window: Window
) -> Iterator[dict[str, object]] | None:
    """The review rows that pay in ``window``; ``None`` if the guard is unreadable.

    ``earner.evidence`` for :data:`~earned_time.REVIEW`, called by
    :func:`~earned_time._ledger.counting_rows` with the review ledger's rows
    already read and the key already loaded.
    """
    reviews = [
        row
        for row in rows
        if isinstance(row, dict)
        and row.get("kind") == "credit"
        and _detail(row).get("source") == REVIEW_SOURCE
        and verified(row, key)
    ]
    today = [row for row in reviews if review_match(row, window)]
    if not today:
        return iter(())
    guard = replace(earner, label="LeetCode guard", missing_ledger_is_no=False)
    guard_rows = read_rows(guard_ledger_for(ledger, earner), guard)
    if guard_rows is None:
        return None
    accepted = _accepted(guard_rows, key)
    firsts = _firsts(reviews)
    paid: list[dict[str, object]] = []
    for row in today:
        slug = _slug(row)
        if slug is None:
            _logger.warning(
                "LeetCode review %r has no title_slug; it pays nothing",
                row.get("entry_id"),
            )
        elif firsts[slug] is row and _pays(row, accepted):
            paid.append(row)
    return iter(paid)


@dataclass(frozen=True)
class ReviewEarner(Earner):
    """The review's earner kind: a top-up paid by :func:`paid_reviews`."""

    @property
    def topup(self) -> bool:
        """Always: never a rung, never in the floor, added last and capped."""
        return True

    @property
    def evidence(self) -> RowEvidence:
        """:func:`paid_reviews`: the guard ledger backs each row."""
        return paid_reviews


# A pure top-up: 0 gaming, no penalty, not on the ladder, not in the floor.
# ``confirmed_on`` stays unset until kuhy has seen a real review credited.
REVIEW: Final = ReviewEarner(
    name="review",
    label="LeetCode review",
    gaming_minutes=0,
    shutdown_minutes=REVIEW_SHUTDOWN_MINUTES,
    ledger=REVIEW_LEDGER,
    match=review_match,
    missing_ledger_is_no=True,
)
