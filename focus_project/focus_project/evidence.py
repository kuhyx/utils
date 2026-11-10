# Copyright (c) 2026 Krzysztof Rudnicki
"""The interview evidence store: append-only rows plus copied files.

One jsonl per project (``{ms, milestone, kind, value}``) under the
:mod:`focus_project._paths` seam. There is deliberately no delete or rewrite
function: a milestone once evidenced stays evidenced.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import itertools
import json
import logging
import os
import re
import shutil
from typing import TYPE_CHECKING

from focus_project import _clock, _paths

if TYPE_CHECKING:
    from pathlib import Path

_LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class Evidence:
    """One evidence row."""

    ms: int
    milestone: str
    kind: str
    value: object

    @property
    def at(self) -> datetime:
        """When it was recorded, as a naive local datetime."""
        return from_ms(self.ms)


def to_ms(moment: datetime) -> int:
    """Unix milliseconds of a naive local datetime."""
    return int(moment.timestamp() * 1000)


def from_ms(ms: int) -> datetime:
    """Naive local datetime of unix milliseconds."""
    return datetime.fromtimestamp(ms / 1000, tz=UTC).astimezone().replace(tzinfo=None)


def clock_now() -> datetime:
    """The clock seam (:mod:`focus_project._clock`) as a naive local datetime."""
    return from_ms(int(_clock.now() * 1000))


def append(
    project_id: str, milestone: str, kind: str, value: object, now: datetime
) -> Evidence:
    """Append one row (fsynced) and return it."""
    row = Evidence(to_ms(now), milestone, kind, value)
    path = _paths.evidence_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(
        {"ms": row.ms, "milestone": milestone, "kind": kind, "value": value}
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return row


def store_file(project_id: str, source: Path, now: datetime) -> str:
    """Copy ``source`` beside the rows under a name that never collides."""
    target = _paths.evidence_files_dir(project_id)
    target.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", source.name)[:80]
    stamp = to_ms(now)
    for attempt in itertools.count():
        name = f"{stamp}-{safe}" if not attempt else f"{stamp}-{attempt}-{safe}"
        try:
            with (target / name).open("xb") as out, source.open("rb") as src:
                shutil.copyfileobj(src, out)
                out.flush()
                os.fsync(out.fileno())
        except FileExistsError:
            continue
        return name
    raise AssertionError  # pragma: no cover (itertools.count never ends)


def _parse(line: str) -> Evidence | None:
    try:
        row = json.loads(line)
        if not isinstance(row, dict) or isinstance(row["ms"], bool):
            return None
        return Evidence(
            int(row["ms"]), str(row["milestone"]), str(row["kind"]), row["value"]
        )
    except ValueError, KeyError, TypeError:
        return None


def read(project_id: str) -> list[Evidence]:
    """Every row in file order; a missing file is empty, bad lines are skipped.

    A torn last line (crash mid-append) must not wipe out the whole history,
    so malformed lines are logged and ignored; an unreadable file raises.
    """
    try:
        path = _paths.evidence_path(project_id)
        text = path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return []
    rows: list[Evidence] = []
    for number, line in enumerate(text.splitlines(), start=1):
        parsed = _parse(line)
        if parsed is None:
            _LOG.warning(
                "evidence %s line %d: skipping malformed row", project_id, number
            )
        else:
            rows.append(parsed)
    return rows


def first(
    rows: list[Evidence], milestone: str, kind: str, since_ms: int = 0
) -> Evidence | None:
    """The earliest matching row at or after ``since_ms``."""
    return next(
        (
            r
            for r in rows
            if (r.milestone, r.kind) == (milestone, kind) and r.ms >= since_ms
        ),
        None,
    )


def last(rows: list[Evidence], milestone: str, kind: str) -> Evidence | None:
    """The latest matching row."""
    return next(
        (r for r in reversed(rows) if (r.milestone, r.kind) == (milestone, kind)),
        None,
    )


def check_summary(
    rows: list[Evidence], milestone: str
) -> tuple[int | None, bool | None, bool]:
    """``(first passing ms, latest verdict, any check row)`` for a milestone."""
    checks = [r for r in rows if (r.milestone, r.kind) == (milestone, "check")]
    passed = next((r.ms for r in checks if r.value is True), None)
    latest = checks[-1].value if checks else None
    return passed, (latest if isinstance(latest, bool) else None), bool(checks)
