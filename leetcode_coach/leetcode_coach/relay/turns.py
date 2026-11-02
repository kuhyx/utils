"""Session start, chat, hint, reveal and run-code (DOCS-coach-relay.md 2).

Every kuhy line is logged (``chat``) and shown before the model is asked,
so the app sees it at once. Code -- typed in chat or sent to run -- is
refused while the relay's own step 2 is neither passed nor forced, checked
BEFORE `PhaseGate.screen`: the gate's own 3-incompletes auto-open must not
skip kuhy's choice to force. Grades waiting for the coach ride as a prefix
on its next turn; ``reveal`` goes out bare, because the Stop gate lifts only
on a message that is exactly ``reveal``.
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
import secrets
from typing import TYPE_CHECKING, Any, Final, NoReturn
import urllib.error

from leetcode_coach import (
    fetch_problem,
    local_prompt,
    phase,
    progress,
    req_check,
    session_log,
)
from leetcode_coach.relay import protocol, steps
from leetcode_coach.relay.errors import CoachError
from leetcode_coach.relay.session import Session

if TYPE_CHECKING:
    from pathlib import Path

    from leetcode_coach.relay.coach import Coach

_logger: Final = logging.getLogger(__name__)

LOCKED: Final = "Code waits until step 2 (requirements) is passed or forced."
RUN_ERRORS: Final = {
    "timeout": "Your code ran past its time limit.",
    "node_missing": "node is not installed on the PC.",
    "no_examples": "No examples could be read from the statement.",
    "syntax": "Your code does not parse (SyntaxError).",
}


def fetch_statement(slug: str) -> tuple[str, str] | None:
    """``(title, statement)`` from LeetCode, in-process; None when unavailable."""
    try:
        question = fetch_problem.fetch(slug)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        _logger.warning("could not fetch %s: %s", slug, exc)
        return None
    if question is None or question.get("isPaidOnly") or not question.get("content"):
        _logger.warning("%s is unknown or premium-only", slug)
        return None
    return str(question["title"]), fetch_problem.render(question, "javascript")


def gate_for(coach: Coach, log: Path, slug: str) -> phase.PhaseGate:
    """The phase gate for one session's log, built directly (never ``open``)."""
    return phase.PhaseGate(log, coach.deps.box(), lambda: slug, coach.deps.ask)


def statement(coach: Coach, session: Session) -> str | None:
    """The session's statement, fetched again if a restart lost it."""
    if session.statement is None and (got := coach.deps.fetch(session.slug)):
        session.statement = got[1]
        session.gate.known = got[1]
    return session.statement


def _sid(now_ms: int) -> str:
    local = datetime.fromtimestamp(now_ms / 1000, tz=UTC).astimezone()
    return f"{local:%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def start(coach: Coach, req: protocol.Request) -> dict[str, Any]:
    """Open a session for ``body.slug``: the coach's opener first."""
    live = coach.session
    if live is not None and live.ended is None:
        msg = "A session is already live; end it first."
        raise CoachError(msg, code="session_live")
    slug = str(req.body["slug"])
    if slug not in coach.deps.answers():
        msg = f"{slug} has no answer key: only the cluster problems are coached here."
        raise CoachError(msg, code="no_answer_key")
    fetched = coach.deps.fetch(slug)
    now = coach.now()
    sid = _sid(now)
    day = datetime.fromtimestamp(now / 1000, tz=UTC).astimezone().date()
    log = session_log.log_path(slug, day)
    session = Session(
        sid=sid,
        slug=slug,
        title=fetched[0] if fetched else slug,
        url=f"https://leetcode.com/problems/{slug}/",
        cluster=progress.cluster_of(slug),
        log=log,
        started=now,
        transport=req.transport,
        dev=req.dev,
        gate=coach.gate_for(log, slug),
        statement=fetched[1] if fetched else None,
    )
    session.gate.known = session.statement
    raw = coach.chat.open(session)
    session.log_event(
        "session_start",
        source="app",
        transport=req.transport,
        dev=req.dev,
        slug=slug,
        at=now,
    )
    key, _rung = _reply(coach, session, raw, "chat")
    coach.session = session
    return {"session": sid, "msg": key}


def _kuhy(coach: Coach, session: Session, kind: str, text: str) -> None:
    now = coach.now()
    session.log_event("chat", role="kuhy", kind=kind, text=text, at=now)
    session.add("kuhy", kind, text, now)


def _reply(
    coach: Coach, session: Session, raw: str, kind: str
) -> tuple[str, str | None]:
    """Log the reply's rung, strip it, show and log the reply."""
    rung = local_prompt.split_rung(raw)[1]
    clean = session.gate.after_reply(raw)
    now = coach.now()
    session.log_event("chat", role="coach", kind=kind, text=clean, at=now)
    return session.add("coach", kind, clean, now), rung


def _prefixed(session: Session, text: str) -> str:
    if not session.notes:
        return text
    notes = "\n".join(session.notes)
    session.notes.clear()
    return f"{notes}\n\n{text}"


def code_open(session: Session) -> bool:
    """Whether the relay's own step 2 is passed or forced."""
    return steps.derive(session.events())[1].done


def _refuse(coach: Coach, session: Session, note: str) -> NoReturn:
    session.add("system", "refused", f"{LOCKED}\n{note}".strip(), coach.now())
    raise CoachError(LOCKED, code="phase_locked", note=note)


def chat(coach: Coach, session: Session, text: str) -> dict[str, Any]:
    """One chat turn; ``hint`` and ``reveal`` typed alone are those kinds."""
    word = text.strip()
    if word in {"hint", "reveal"}:
        _kuhy(coach, session, word, word)
        coach.publish()
        if word == "hint":
            key, rung = _reply(
                coach, session, coach.chat.turn(session, _prefixed(session, word)), word
            )
            return {"msg": key, "rung": rung}
        session.gate.screen(word)  # logs ``reveal``, as the REPL does
        session.notes.clear()
        key, _rung = _reply(coach, session, coach.chat.turn(session, word), word)
        coach.end(session, "reveal")
        return {"msg": key}
    is_code = phase.regex_verdict(word)
    if is_code is None:
        is_code = req_check.looks_like_code(word, coach.deps.ask)
    _kuhy(coach, session, "chat", text)
    if is_code and not code_open(session):
        _refuse(coach, session, session.gate.refusal_note())
    sent, note = session.gate.screen(text, is_code=is_code)
    if sent is None:
        _refuse(coach, session, note)
    if note:
        session.add("system", "grade", note, coach.now())
    coach.publish()
    raw = coach.chat.turn(session, _prefixed(session, sent))
    key, _rung = _reply(coach, session, raw, "chat")
    return {"msg": key}


def run_code(coach: Coach, session: Session, code: str) -> dict[str, Any]:
    """Run kuhy's JavaScript against the statement's examples."""
    if not code_open(session):
        _refuse(coach, session, session.gate.refusal_note())
    session.log_event("code", via="run", at=coach.now())
    result = coach.deps.run_code(code, statement(coach, session) or "")
    lines = [
        f"example {r['n']}: got {r['got']}, expected {r['expected']}"
        for r in result.get("examples", [])
    ]
    if result.get("error"):
        lines.append(RUN_ERRORS.get(str(result["error"]), str(result["error"])))
    session.add("system", "run", "\n".join(lines), coach.now())
    return result
