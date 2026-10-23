"""The req-before-code phase gate, run by the REPL on both paths.

TODO-coach.md decisions 4-6: a message starting ``req:`` is kuhy's
requirement list. Until one is accepted, a block that is code is refused
here, with a one-line reason, and never reaches the coach model. A list is
accepted when the checker passes it or cannot judge it (fail open); after the
3rd list that still comes back incomplete, code is let through anyway and its
``code`` event carries ``req_incomplete: true``.

State is derived from the session log, not held in memory, so it survives the
mid-session hand-over to the local model and a restarted REPL the same day.
The ``code`` event is appended BEFORE the block is sent: the Stop hook judges
the reply to that very block and reads the log to know code exists.

Is a block code? A regex decides the clear cases; only a block it cannot
decide goes to the model (`req_check.looks_like_code`), and an unanswered
question is "not code" -- the gate never refuses kuhy on a guess.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
import re
from typing import TYPE_CHECKING, Any

from leetcode_coach import (
    leak,
    local_prompt,
    local_session,
    req_check,
    session_log,
    toolbox,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

MAX_LISTS = 3
REQ_RE = re.compile(r"^\s*req\s*:", re.IGNORECASE)
STRONG_RE = re.compile(
    r"```|=>|^\s*(?:function\b|def\s+\w+\s*\(|class\s+\w+|"
    r"(?:const|let|var)\s+\w+\s*=|(?:for|while|if)\s*\(|#include|import\s+\w)"
    r"|[;{]\s*$|^\s*\}",
    re.MULTILINE,
)
OPERATOR_RE = re.compile(
    r"\w\s*(?:[=!]==?|<=|>=|[-+*/%^&|]=|\^|&&|\|\||<<|>>|%|=)\s*\w|\w\(|\w\["
)


def regex_verdict(block: str) -> bool | None:
    """True for clear code, False for clear prose, None when it cannot tell."""
    if REQ_RE.match(block):
        return False
    if STRONG_RE.search(block):
        return True
    return None if OPERATOR_RE.search(block) else False


@dataclass(frozen=True)
class ReqState:
    """Where the requirement phase stands, derived from the log."""

    accepted: bool
    forced: bool
    tries: int

    @property
    def open(self) -> bool:
        """Whether code may reach the coach."""
        return self.accepted or self.forced


REQ_STEP = 2
"""The app's step 2 (requirements) in ``grade`` events."""


def _step2_grades(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        e for e in events if e.get("event") == "grade" and e.get("step") == REQ_STEP
    ]


def req_state(events: list[dict[str, Any]]) -> ReqState:
    """Accepted on a pass/unverified check; forced after `MAX_LISTS` incompletes.

    A step-2 ``grade`` with ``forced: true`` (the app's "continue anyway")
    forces it too, or a forced step 2 would still refuse kuhy's code.
    """
    verdicts = [e.get("verdict") for e in events if e.get("event") == "req_check"]
    tries = verdicts.count("incomplete")
    accepted = "pass" in verdicts or "unverified" in verdicts
    pushed = any(e.get("forced") is True for e in _step2_grades(events))
    forced = not accepted and (tries >= MAX_LISTS or pushed)
    return ReqState(accepted, forced, tries)


def step2_attempts(events: list[dict[str, Any]]) -> int:
    """Failed step-2 tries: incomplete lists plus app ``fail`` grades.

    A ``fail`` (the list read as code, or named an operation) never reaches
    the checker, so it has no ``req_check``; a ``partial`` does, and is
    already counted there. CLI and app count one file alike.
    """
    fails = sum(1 for e in _step2_grades(events) if e.get("grade") == "fail")
    return req_state(events).tries + fails


def property_line(prop: str, box: toolbox.Toolbox) -> str:
    """`prop: meaning`, or just `prop` when the meaning names an entry.

    Some meanings illustrate with the operation itself (self-inverse:
    "a ^ x ^ x = a"); shown to kuhy that is the answer, not a property.
    """
    meaning = box.properties[prop]
    return prop if leak.leaked_names(meaning, [], box) else f"{prop}: {meaning}"


def _req_note(result: req_check.Check, state: ReqState, box: toolbox.Toolbox) -> str:
    if result.verdict == "pass":
        return "[req list accepted -- code is open]"
    if result.verdict == "unverified":
        return "[req check unavailable -- continuing unverified, code is open]"
    if state.forced:
        missing = ", ".join(result.missing)
        return f"[req list still incomplete ({missing}) -- code accepted anyway]"
    props = "\n".join(f"  - {property_line(p, box)}" for p in result.missing)
    return (
        f"[req list incomplete -- it does not yet say these properties:\n{props}\n"
        f" revise with req: ({state.tries} of {MAX_LISTS})]"
    )


@dataclass
class PhaseGate:
    """One problem's gate: its log, toolbox and (lazily fetched) statement."""

    log: Path
    toolbox: toolbox.Toolbox
    source: Callable[[], str]
    ask: Callable[..., dict[str, Any]] | None = None
    known: str | None = field(default=None, repr=False)

    @classmethod
    def open(cls, problem: str) -> PhaseGate:
        """The gate for `problem`; exports its log path for the Stop hook."""
        log = session_log.log_path(problem)
        os.environ[session_log.LOG_ENV] = str(log)

        def source() -> str:
            return local_session.fetched_statement(problem) or session_log.slug(problem)

        return cls(log, toolbox.load_safe(), source)

    def statement(self) -> str:
        """The problem statement, fetched once on first use."""
        if self.known is None:
            self.known = self.source()
        return self.known

    def events(self) -> list[dict[str, Any]]:
        """This session's log events (`session_log.current`)."""
        return session_log.current(session_log.read(self.log))

    def code_seen(self) -> bool:
        """Whether a code block has been let through this session."""
        return session_log.has_code(self.log)

    def screen(
        self, block: str, *, is_code: bool | None = None
    ) -> tuple[str | None, str]:
        """(what to send the coach, or None to refuse; a note for kuhy).

        `is_code` is a verdict the caller already reached (the relay judges a
        message before its own step-2 check), so the model is not asked twice.
        """
        text = block.strip()
        if text.lower() == "reveal":
            session_log.append(self.log, "reveal")
            return block, ""
        if REQ_RE.match(text):
            return self._req(block)
        verdict = regex_verdict(text) if is_code is None else is_code
        if verdict is None:
            verdict = req_check.looks_like_code(text, self.ask)
        if not verdict:
            return block, ""
        state = req_state(self.events())
        if not state.open:
            return None, self._refusal(state)
        extra = {"req_incomplete": True} if state.forced else {}
        session_log.append(self.log, "code", **extra)
        return block, ""

    def _req(self, block: str) -> tuple[str, str]:
        session_log.append(self.log, "req", text=block.strip())
        result = req_check.check(self.statement(), block, self.toolbox, self.ask)
        session_log.append(
            self.log,
            "req_check",
            verdict=result.verdict,
            missing=list(result.missing),
            via=result.via,
        )
        state = req_state(self.events())
        tag = result.verdict
        if result.missing:
            tag += "; missing properties: " + ", ".join(result.missing)
        return f"{block}\n\n[req check: {tag}]", _req_note(result, state, self.toolbox)

    def refusal_note(self) -> str:
        """The line a refused code block gets now (the relay's ``note``)."""
        return self._refusal(req_state(self.events()))

    @staticmethod
    def _refusal(state: ReqState) -> str:
        if not state.tries:
            return (
                "[code held back: write the requirement list first -- one message "
                "starting with req: that lists the properties the operation must "
                "have, without naming an operation or structure]"
            )
        return (
            "[code held back: the req list is still incomplete -- revise it "
            f"with req: ({state.tries} of {MAX_LISTS} so far)]"
        )

    def after_reply(self, text: str) -> str:
        """Log the reply's rung marker and return the reply without it."""
        clean, rung = local_prompt.split_rung(text)
        if rung is not None:
            session_log.append(self.log, "rung", rung=rung)
        return clean

    def leaks(self, reply: str, user_texts: list[str]) -> list[str]:
        """Toolbox entries `reply` names too early (the local path's bounce)."""
        if any(t.strip() == "reveal" for t in user_texts) or self.code_seen():
            return []
        return leak.leaked_names(reply, user_texts, self.toolbox)
