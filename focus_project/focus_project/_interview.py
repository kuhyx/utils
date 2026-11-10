# Copyright (c) 2026 Krzysztof Rudnicki
"""Validation of the interview-only fields."""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from focus_project._kind import FOCUS, KINDS, WEEKDAY_MINUTES

if TYPE_CHECKING:
    from focus_project._model import Project

MAX_URL = 2000
SATURDAY = 5


def check_http_url(url: str, label: str) -> None:
    """Empty, or a plain http(s) URL with a host: it goes to ``xdg-open``."""
    if not url:
        return
    parts = urlsplit(url) if url.isprintable() and " " not in url else None
    if (
        parts is None
        or len(url) > MAX_URL
        or parts.scheme not in {"http", "https"}
        or not parts.netloc
    ):
        msg = f"{label} must be an http(s) URL without spaces (or empty)"
        raise ValueError(msg)


def saturdays(project: Project) -> list[date]:
    """The Saturdays whose weekend lies inside D1..T-1."""
    if project.test_at is None:
        return []
    last = project.test_at.date() - timedelta(days=1)
    day = project.start + timedelta(days=(SATURDAY - project.start.weekday()) % 7)
    found: list[date] = []
    while day <= last:
        found.append(day)
        day += timedelta(days=7)
    return found


def _has_interview_fields(project: Project) -> bool:
    return bool(
        project.test_at
        or project.invite_url
        or project.trips
        or project.weekend_answers
    )


def _validate_interview(project: Project) -> None:
    if project.test_at is None or project.test_at.tzinfo is not None:
        msg = "an interview needs test_at as a naive local datetime"
        raise ValueError(msg)
    test_day = project.test_at.date()
    if project.end != test_day:
        msg = f"end must be the test day {test_day}"
        raise ValueError(msg)
    if project.daily_minutes < WEEKDAY_MINUTES:
        msg = f"daily_minutes must be at least {WEEKDAY_MINUTES}"
        raise ValueError(msg)
    for trip in project.trips:
        if trip.end < trip.start or trip.start > test_day:
            msg = f"trip {trip.start}..{trip.end} must start by the test day"
            raise ValueError(msg)
    weekends = saturdays(project)
    for day, _ in project.weekend_answers:
        if day not in weekends:
            msg = f"{day} is not a weekend inside the project before the test day"
            raise ValueError(msg)


def validate(project: Project) -> None:
    """ValueError unless the kind and its interview fields are coherent."""
    if project.kind not in KINDS:
        msg = f"kind must be one of {sorted(KINDS)}"
        raise ValueError(msg)
    check_http_url(project.invite_url, "invite_url")
    if project.kind == FOCUS:
        if _has_interview_fields(project):
            msg = "test_at, invite_url, trips, weekend_answers need kind='interview'"
            raise ValueError(msg)
        return
    _validate_interview(project)
