"""The coach's per-problem session log (TODO-coach.md decision 8).

One JSONL file per problem and day,
``~/.local/share/leetcode-coach/sessions/<YYYY-MM-DD>-<slug>.jsonl`` (the
directory follows ``LEETCODE_COACH_SESSIONS_DIR``: `progress.sessions_dir`).
Every line is one object with ``event`` and ``ts``; ``req_check`` carries ``verdict``,
``rung`` carries ``rung``. That contract is FIXED: ``leetcode_guard._coach_log``
reads it for the status app, so a new kind of fact rides as an extra field on
an existing event (``code`` + ``req_incomplete``), and new names only together
with the reader: ``session_start``, ``grade``, ``chat`` and ``session_end``
came with ``_coach_log.EVENTS`` in one commit (DOCS-coach-relay.md section 5).
A file can hold several app sessions; each starts at its ``session_start``
(`current`), and a CLI-only file is one session.

Every event carries ``cluster`` while ``LEETCODE_COACH_CLUSTER`` is set
(`leetcode --cluster` sets it for the session it starts).

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

from leetcode_coach import fetch_problem, progress

_LOG = logging.getLogger(__name__)

LOG_ENV = "LEETCODE_COACH_LOG"
"""Set by the REPL so the Stop hook (a grandchild) reads the same log."""
EVENTS = frozenset(
    {
        *("req", "req_check", "code", "rung", "reveal", "postmortem", "retest"),
        *("session_start", "grade", "chat", "session_end"),
    }
)


def sessions_dir() -> Path:
    """Where the session files live (one definition: `progress.sessions_dir`)."""
    return progress.sessions_dir()


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
    cluster = os.environ.get(progress.CLUSTER_ENV)
    stamped = {"cluster": cluster} if cluster else {}
    record = {"event": event, "ts": stamp, **stamped, **fields}
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


def current(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The events of the file's latest session: from its last ``session_start``."""
    starts = [i for i, e in enumerate(events) if e.get("event") == "session_start"]
    return events[starts[-1] :] if starts else events


def has_code(path: Path) -> bool:
    """Whether kuhy's code has reached the coach in this session."""
    return any(e.get("event") == "code" for e in current(read(path)))


def append_current(event: str, **fields: object) -> bool:
    """Append to the log the REPL exported (`LOG_ENV`); False outside a session.

    For writers that run as the coach's grandchildren, like the card builder
    logging ``postmortem`` once the cards are delivered. The TUI has no REPL
    and so no log: nothing is written there.
    """
    exported = os.environ.get(LOG_ENV)
    if not exported:
        return False
    append(Path(exported), event, **fields)
    return True
