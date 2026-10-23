"""The coach's per-problem session log (TODO-coach.md decision 8).

One JSONL file per problem and day,
``~/.local/share/leetcode-coach/sessions/<YYYY-MM-DD>-<slug>.jsonl`` (the
directory follows ``LEETCODE_COACH_SESSIONS`` when set, for tests). Every line
is one object with ``event`` and ``ts``; ``req_check`` carries ``verdict``,
``rung`` carries ``rung``. That contract is FIXED: ``leetcode_guard._coach_log``
reads it for the status app, so a new kind of fact rides as an extra field on
an existing event (``code`` + ``req_incomplete``), never as a new event name.

Appends are one ``os.write`` on an ``O_APPEND`` descriptor, so a concurrent
reader sees whole lines, and two writers (REPL and a hook) cannot interleave.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
import json
import logging
import os
from pathlib import Path
import re
from typing import Any

from leetcode_coach import fetch_problem

_LOG = logging.getLogger(__name__)

SESSIONS_ENV = "LEETCODE_COACH_SESSIONS"
LOG_ENV = "LEETCODE_COACH_LOG"
"""Set by the REPL so the Stop hook (a grandchild) reads the same log."""
DEFAULT_DIR = Path.home() / ".local" / "share" / "leetcode-coach" / "sessions"
EVENTS = frozenset(
    {"req", "req_check", "code", "rung", "reveal", "postmortem", "retest"}
)


def sessions_dir() -> Path:
    """Where the session files live."""
    return Path(os.environ.get(SESSIONS_ENV) or DEFAULT_DIR)


def slug(problem: str) -> str:
    """The LeetCode slug in `problem`, or a filesystem-safe stand-in."""
    try:
        return fetch_problem.slug_from(problem)
    except ValueError as exc:
        _LOG.warning("%s; naming the log after a sanitised copy", exc)
        return re.sub(r"[^a-z0-9]+", "-", problem.lower()).strip("-") or "problem"


def log_path(problem: str, day: date | None = None) -> Path:
    """The log file for `problem` (URL or slug) on `day` (default today)."""
    when = day or datetime.now(tz=UTC).astimezone().date()
    return sessions_dir() / f"{when.isoformat()}-{slug(problem)}.jsonl"


def append(path: Path, event: str, **fields: object) -> None:
    """Append one event line atomically.

    Raises:
        ValueError: for an event name outside the fixed contract.
    """
    if event not in EVENTS:
        msg = f"{event!r} is not a session-log event; add a field instead"
        raise ValueError(msg)
    stamp = datetime.now(tz=UTC).astimezone().isoformat(timespec="seconds")
    record = {"event": event, "ts": stamp, **fields}
    line = (json.dumps(record, ensure_ascii=False) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, line)
    finally:
        os.close(fd)


def _parse(line: str) -> object:
    try:
        return json.loads(line)
    except ValueError as exc:
        _LOG.warning("session log line is not JSON, skipped: %s", exc)
        return None


def read(path: Path) -> list[dict[str, Any]]:
    """Every object line in `path`; nothing when it does not exist yet."""
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    parsed = (_parse(line) for line in lines if line.strip())
    return [obj for obj in parsed if isinstance(obj, dict)]


def has_code(path: Path) -> bool:
    """Whether kuhy's code has reached the coach in this session."""
    return any(e.get("event") == "code" for e in read(path))
