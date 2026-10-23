"""The live coaching session: what the log cannot hold, and its pointer file.

Steps, grades, rung and reveal are derived from the session log every time
(`steps`); a `Session` adds what only the relay knows -- the claude session
id, the chat lines in display order, notes waiting for the coach's next turn
and the Accepted probe. ``live.json`` points at the live session (sid, log,
claude id, rev) so a restarted relay rebuilds it from the log: chat lines
from the ``chat`` and ``grade`` events, the rest re-derived.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from leetcode_coach import session_log
from leetcode_coach.relay.steps import NAMES

if TYPE_CHECKING:
    from collections.abc import Callable

    from leetcode_coach.local_coach import LocalCoach
    from leetcode_coach.phase import PhaseGate

_logger: Final = logging.getLogger(__name__)

LIVE_FIELDS: Final = (
    "sid",
    "slug",
    "title",
    "url",
    "cluster",
    "started",
    "transport",
    "dev",
    "claude_id",
    "local",
)


@dataclass
class Session:  # pylint: disable=too-many-instance-attributes
    """One problem's coaching session."""

    sid: str
    slug: str
    title: str
    url: str
    cluster: str | None
    log: Path
    started: int
    transport: str
    dev: str
    gate: PhaseGate
    statement: str | None = None
    claude_id: str | None = None
    local: bool = False
    ended: int | None = None
    end_reason: str | None = None
    chat: dict[str, dict[str, Any]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    history: list[dict[str, str]] = field(default_factory=list)
    local_coach: LocalCoach | None = None
    probe: str | None = None
    probed_at: int | None = None

    def events(self) -> list[dict[str, Any]]:
        """This session's log events (from its ``session_start`` on)."""
        return session_log.current(session_log.read(self.log))

    def add(self, role: str, kind: str, text: str, at: int) -> str:
        """Append one chat line (empty fields dropped); its ``m0001`` key."""
        key = f"m{len(self.chat) + 1:04d}"
        line = {"role": role, "kind": kind, "text": text, "at": at}
        self.chat[key] = {k: v for k, v in line.items() if v not in ("", None)}
        return key

    def log_event(self, event: str, **fields: object) -> None:
        """Append `event` to the log with this session's sid and cluster."""
        extra = {"cluster": self.cluster} if self.cluster else {}
        session_log.append(self.log, event, sid=self.sid, **extra, **fields)

    def info(self) -> dict[str, Any]:
        """The ``session`` block of the published state."""
        return {
            "id": self.sid,
            "slug": self.slug,
            "title": self.title,
            "cluster": self.cluster,
            "url": self.url,
            "started": self.started,
            "ended": self.ended,
            "end_reason": self.end_reason,
        }


def save(path: Path, session: Session, rev: int) -> None:
    """Write the live pointer (atomically: a torn pointer loses the session)."""
    record = {k: getattr(session, k) for k in LIVE_FIELDS}
    record |= {"log": str(session.log), "rev": rev}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(record), encoding="utf-8")
    tmp.replace(path)


def _ms(event: dict[str, Any]) -> int:
    at = event.get("at")
    if isinstance(at, int):
        return at
    try:
        return int(datetime.fromisoformat(str(event.get("ts"))).timestamp() * 1000)
    except ValueError as exc:
        _logger.warning("event without a usable time: %s", exc)
        return 0


def grade_line(event: dict[str, Any]) -> tuple[str, str]:
    """The ``system`` chat line a step's grade shows as."""
    step = int(event["step"])
    name = NAMES.get(step, "step")
    if event.get("via") == "accepted":
        return "accepted", f"Step 4 ({name}): LeetCode shows an Accepted. Step 5 open."
    if event.get("forced") is True:
        tries = event.get("attempt")
        return "grade", f"Step {step} ({name}): continued after {tries} tries."
    head = f"Step {step} ({name}): {event.get('grade')} on try {event.get('attempt')}."
    feedback = str(event.get("feedback") or "")
    return "grade", f"{head}\n{feedback}".strip()


def restore(
    path: Path, gate_for: Callable[[Path, str], PhaseGate]
) -> tuple[Session, int] | None:
    """The session ``live.json`` points at, rebuilt from its log; None if gone."""
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        log = Path(raw["log"])
        fields = {k: raw[k] for k in LIVE_FIELDS}
        rev = int(raw.get("rev", 0))
    except (ValueError, KeyError, TypeError) as exc:
        _logger.warning("live session pointer %s is unusable: %s", path, exc)
        return None
    session = Session(**fields, log=log, gate=gate_for(log, raw["slug"]))
    events = session.events()
    if not events or events[0].get("sid") != session.sid:
        _logger.warning("live session %s is not the log's latest", session.sid)
        return None
    for event in events:
        if event["event"] == "chat":
            role, kind = str(event.get("role")), str(event.get("kind", "chat"))
            session.add(role, kind, str(event.get("text", "")), _ms(event))
            who = "user" if role == "kuhy" else "assistant"
            session.history.append({"role": who, "content": str(event["text"])})
        elif event["event"] == "grade":
            kind, text = grade_line(event)
            session.add("system", kind, text, _ms(event))
        elif event["event"] == "session_end":
            session.ended = _ms(event)
            session.end_reason = str(event.get("reason"))
    return session, rev
