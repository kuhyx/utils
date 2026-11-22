# Copyright (c) 2026 Krzysztof Rudnicki
"""One digest per (registry, day) of everything ``resolve`` answers.

Standalone on purpose: it imports only ``earned_time``, so the same file runs
in-process against the working tree and, as ``python -P _grid_dump.py`` from
another directory, against whatever ``earned_time`` the interpreter installed
(the 0.23.0 oracle of ``test_progress_dark``). It touches no live state: the
leisure switch file and the focus project are stood in for.
"""

from __future__ import annotations

from datetime import date, timedelta
import hashlib
import itertools
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import earned_time

FOCUS = SimpleNamespace(
    start=date(2026, 11, 1), daily_minutes=120, replaces=("book", "leetcode")
)
# Around every dated switch: the ladder, the tutor, the waiver, unified pay,
# the focus start, no gaming budget, the review top-up, the parked leisure day.
SPOTS = (
    date(2026, 9, 25),
    date(2026, 9, 26),
    date(2026, 10, 1),
    date(2026, 10, 5),
    date(2026, 10, 6),
    date(2026, 10, 8),
    date(2026, 10, 9),
    date(2026, 10, 10),
    date(2026, 10, 17),
    date(2026, 10, 18),
    date(2026, 11, 1),
    date(2026, 11, 8),
    date(2026, 11, 15),
    date(2026, 11, 16),
    date(2026, 11, 22),
    date(2026, 11, 23),
    date(2026, 11, 24),
    date(2026, 12, 25),
    date(2027, 1, 1),
    date(2027, 1, 2),
)
DAYS = tuple(
    sorted({*SPOTS, *(date(2026, 11, 14) + timedelta(days=n) for n in range(14))})
)
OPTIONS: tuple[int | None, ...] = (None, 0, 1, 60)
# From this day a credited review with no progress row pays nothing, which is
# not 0.23.0's answer (REVIEW_PROGRESS_FROM, a literal: 0.23.0 has no such name).
# From it the review is only asked "no" and "could not check", which agree.
REVIEW_PROGRESS_FROM = date(2026, 11, 24)
REVIEW_OPTIONS: tuple[int | None, ...] = (None, 0)


def _registry(mode: str, day: date) -> tuple[earned_time.Earner, ...]:
    if mode == "legacy":
        return earned_time.EARNERS
    if mode == "tutor":
        return earned_time.TUTOR_EARNERS
    return earned_time.earners_for(day)


def _lines(mode: str, day: date, extra: dict[str, object]) -> list[str]:
    registry = _registry(mode, day)
    names = [e.name for e in registry]
    explicit = None if mode == "default" else registry
    out = [repr(earned_time.base_for(day, explicit))]
    options = [
        REVIEW_OPTIONS if name == "review" and day >= REVIEW_PROGRESS_FROM else OPTIONS
        for name in names
    ]
    for values in itertools.product(*options):
        answers = dict(zip(names, values, strict=True))
        for sick, leisure in ((False, None), (True, None), (False, True)):
            res = earned_time.resolve(
                answers, day, explicit, sick=sick, leisure=leisure, **extra
            )
            terms = [
                (t.earner.name, t.answer, t.gaming_minutes, t.shutdown_minutes)
                for t in res.terms
            ]
            out.append(
                repr(
                    (
                        res.day,
                        res.base,
                        terms,
                        res.gaming_minutes,
                        res.shutdown_minutes,
                        res.sick,
                        res.sick_lift_minutes,
                        res.gaming_enforced,
                    )
                )
            )
    return out


def dump(**extra: object) -> dict[str, str]:
    """``"mode|day"`` -> sha256 of every resolution of that registry and day.

    ``extra`` is passed to every ``resolve`` (the new ``progress=``).
    """
    digests: dict[str, str] = {}
    with TemporaryDirectory() as tmp:
        earned_time._leisure.LEISURE_FROM_PATH = Path(tmp) / "missing"
        for mode in ("default", "legacy", "tutor", "focus"):
            sys.modules["focus_project"] = SimpleNamespace(
                active=lambda _d, on=mode == "focus": FOCUS if on else None
            )
            for day in DAYS:
                name = "default" if mode == "focus" else mode
                body = "\n".join(_lines(name, day, extra))
                digests[f"{mode}|{day}"] = hashlib.sha256(body.encode()).hexdigest()
    return digests


if __name__ == "__main__":
    sys.stdout.write(json.dumps(dump(), indent=0, sort_keys=True) + "\n")
