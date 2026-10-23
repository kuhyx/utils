"""Cluster progress and the cold re-test schedule, derived from the session logs.

TODO-coach.md decisions 10 and 12. Nothing here keeps state of its own: the
JSONL session logs (``<YYYY-MM-DD>-<slug>.jsonl``, decision 8) are the only
record, so progress survives anything that survives the logs.

* A problem is **started** once it has a ``code`` event, and **solved** on the
  first day by which it has both a ``code`` and a ``postmortem`` event. A
  later re-test session logs its own code and post-mortem; that never moves
  the solve day, so it cannot reset the schedule.
* Re-tests fall due ``RETEST_OFFSETS`` days after the solve day (+3, +10).
  Each ``retest`` event completes one stage.

Days come from the file name, like ``leetcode_guard._coach_log``: the ``ts``
field's format belongs to the session writer. Stdlib only, because the status
snapshot imports this every minute on the system python.
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import json
import logging
import os
from pathlib import Path
import re
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Callable

_LOG: Final = logging.getLogger(__name__)

SESSIONS_ENV: Final = "LEETCODE_COACH_SESSIONS_DIR"
CLUSTER_ENV: Final = "LEETCODE_COACH_CLUSTER"
"""Set for the coached session; the session writer stamps it as ``cluster``."""
DEFAULT_SESSIONS_DIR: Final = (
    Path.home() / ".local" / "share" / "leetcode-coach" / "sessions"
)
CLUSTERS_PATH: Final = Path(__file__).with_name("clusters.json")
RETEST_OFFSETS: Final = (3, 10)
_DATED: Final = re.compile(r"(?P<day>\d{4}-\d{2}-\d{2})-(?P<slug>.+)")

Event = dict[str, Any]


@dataclass(frozen=True)
class History:
    """What the logs say about one problem."""

    started: bool
    solved: dt.date | None
    retests: int


def sessions_dir() -> Path:
    """Where the session logs live (``$LEETCODE_COACH_SESSIONS_DIR`` overrides)."""
    override = os.environ.get(SESSIONS_ENV)
    return Path(override) if override else DEFAULT_SESSIONS_DIR


def local_today() -> dt.date:
    """Today in local time: a re-test is due by kuhy's calendar, not UTC's."""
    return dt.datetime.now(tz=dt.UTC).astimezone().date()


def load_clusters(path: Path | None = None) -> dict[str, list[dict[str, Any]]]:
    """``{"<cluster>": [{"id": 268, "slug": "missing-number"}, ...]}``, in order."""
    source = CLUSTERS_PATH if path is None else path
    clusters: dict[str, list[dict[str, Any]]] = json.loads(
        source.read_text(encoding="utf-8")
    )["clusters"]
    return clusters


def cluster_of(slug: str) -> str | None:
    """The cluster a problem belongs to, if any."""
    for name, problems in load_clusters().items():
        if any(p["slug"] == slug for p in problems):
            return name
    return None


def _dated(path: Path) -> tuple[dt.date, str] | None:
    """``2026-10-23-missing-number.jsonl`` -> (date, slug); None if undated."""
    match = _DATED.fullmatch(path.stem)
    if match is None:
        return None
    try:
        return dt.date.fromisoformat(match["day"]), match["slug"]
    except ValueError:
        _LOG.warning("coach session %s has an impossible date; skipped", path)
        return None


def _parse(path: Path, line: str) -> Event | None:
    """One log line as an event; None for anything that is not one."""
    try:
        event = json.loads(line)
    except ValueError as exc:
        # A torn line is a writer that died mid-write: worth its own warning.
        _LOG.warning("coach session %s: a line is not JSON: %s", path, exc)
        return None
    if isinstance(event, dict) and isinstance(event.get("event"), str):
        return event
    return None


def _events(path: Path) -> list[Event]:
    """The file's events in order; unreadable files and junk lines are skipped."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        _LOG.warning("coach session %s is unreadable: %s", path, exc)
        return []
    parsed = (_parse(path, line) for line in lines if line.strip())
    return [event for event in parsed if event is not None]


def _read(directory: Path | None) -> dict[str, list[tuple[dt.date, Event]]]:
    """Every slug's events across all its files, oldest file first."""
    folder = sessions_dir() if directory is None else directory
    by_slug: dict[str, list[tuple[dt.date, Event]]] = {}
    if not folder.is_dir():
        return by_slug
    for path in sorted(folder.glob("*.jsonl")):
        if (dated := _dated(path)) is not None:
            day, slug = dated
            by_slug.setdefault(slug, []).extend((day, e) for e in _events(path))
    return by_slug


def _history(entries: list[tuple[dt.date, Event]]) -> History:
    seen: set[str] = set()
    solved: dt.date | None = None
    for day, event in entries:
        seen.add(event["event"])
        if solved is None and {"code", "postmortem"} <= seen:
            solved = day
    retests = sum(event["event"] == "retest" for _day, event in entries)
    return History(started="code" in seen, solved=solved, retests=retests)


def history(slug: str, directory: Path | None = None) -> History:
    """Started / solved day / re-tests done for one problem."""
    return _history(_read(directory).get(slug, []))


def count_events(slug: str, kind: str, directory: Path | None = None) -> int:
    """How many ``kind`` events the problem has across all its files."""
    return sum(event["event"] == kind for _d, event in _read(directory).get(slug, []))


def due_retests(
    directory: Path | None = None, today: dt.date | None = None
) -> list[dict[str, Any]]:
    """Re-tests due by ``today``, oldest due date first."""
    day = local_today() if today is None else today
    rows: list[dict[str, Any]] = []
    for slug, entries in _read(directory).items():
        past = _history(entries)
        if past.solved is None or past.retests >= len(RETEST_OFFSETS):
            continue
        due = past.solved + dt.timedelta(days=RETEST_OFFSETS[past.retests])
        if due <= day:
            rows.append(
                {
                    "slug": slug,
                    "cluster": cluster_of(slug),
                    "stage": past.retests + 1,
                    "due": due.isoformat(),
                    "solved": past.solved.isoformat(),
                }
            )
    return sorted(rows, key=lambda row: (row["due"], row["slug"]))


def cluster_progress(directory: Path | None = None) -> dict[str, dict[str, Any]]:
    """Per cluster: problems total / started / solved, and the next unstarted one."""
    logs = _read(directory)
    summary: dict[str, dict[str, Any]] = {}
    for name, problems in load_clusters().items():
        pasts = [_history(logs.get(p["slug"], [])) for p in problems]
        fresh = [
            p["slug"] for p, h in zip(problems, pasts, strict=True) if not h.started
        ]
        summary[name] = {
            "total": len(problems),
            "started": sum(h.started for h in pasts),
            "solved": sum(h.solved is not None for h in pasts),
            "next": fresh[0] if fresh else None,
        }
    return summary


def next_new(
    name: str, directory: Path | None, accepted: Callable[[str], bool]
) -> str | None:
    """The cluster's first problem with no ``code`` event that is not Accepted."""
    logs = _read(directory)
    for problem in load_clusters()[name]:
        slug = str(problem["slug"])
        if not _history(logs.get(slug, [])).started and not accepted(slug):
            return slug
    return None


def append_event(slug: str, event: Event) -> Path:
    """Append one event (stamped with ``ts``) to today's session file."""
    folder = sessions_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{local_today().isoformat()}-{slug}.jsonl"
    stamp = dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds")
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({**event, "ts": stamp}, ensure_ascii=False) + "\n")
    return path
