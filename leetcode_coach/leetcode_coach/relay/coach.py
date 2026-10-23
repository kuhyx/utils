"""The session backend every request runs against (DOCS-coach-relay.md 2-3).

One live session at a time. `handle` runs one validated request under the
backend's lock (the lane already serialises; the lock also fences the
Accepted ticker), then republishes the state: ``rev`` moves only when
something visible changed, and listeners (the phone mirror) hear about it.
Readers -- ``GET /coach/state`` and the heartbeat -- take the published copy
and never wait for a model call in progress.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
import threading
from typing import TYPE_CHECKING, Any, Final

from leetcode_coach import answer_key, claude_cli, local_backend, toolbox
from leetcode_coach.relay import config, grading, protocol, runcode, steps, turns
from leetcode_coach.relay.chat import REQUEST_CAP_S, CoachChat
from leetcode_coach.relay.errors import CoachError
from leetcode_coach.relay.probe import ACCEPTED, AcceptedProbe
from leetcode_coach.relay.session import Session, grade_line, restore, save

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from leetcode_coach.phase import PhaseGate

_logger: Final = logging.getLogger(__name__)

ACCEPTED_NOTE: Final = "[app: step 4 passed, LeetCode shows an Accepted; step 5 open]"


def _toolbox() -> toolbox.Toolbox:
    """`toolbox.load_safe`, looked up per call (tests swap the fixture in)."""
    return toolbox.load_safe()


@dataclass
class Deps:
    """Everything the backend talks to; each one a test seam."""

    state_dir: Path = field(default_factory=config.state_dir)
    ask: Callable[..., dict[str, Any]] = claude_cli.ask
    local_chat: Callable[..., local_backend.LocalReply] = local_backend.chat
    fetch: Callable[[str], tuple[str, str] | None] = turns.fetch_statement
    probe: AcceptedProbe = field(default_factory=AcceptedProbe)
    run_code: Callable[[str, str], dict[str, Any]] = runcode.run
    cards_dry_run: bool = field(default_factory=config.cards_dry_run)
    clock_ms: Callable[[], int] = config.now_ms
    answers: Callable[[], dict[str, answer_key.Answer]] = answer_key.load_answers
    box: Callable[[], toolbox.Toolbox] = field(default=_toolbox)


class Coach:
    """The live session, its published state, and the request handlers."""

    def __init__(self, deps: Deps) -> None:
        """Rebuild the live session from ``live.json`` if there is one."""
        self.deps = deps
        self.chat = CoachChat(deps.ask, deps.local_chat)
        self.lock = threading.RLock()
        self.listeners: list[Callable[[dict[str, Any], Session | None], None]] = []
        self.live_path = deps.state_dir / "live.json"
        restored = restore(self.live_path, self.gate_for)
        self.session: Session | None = None if restored is None else restored[0]
        self.rev = 0 if restored is None else restored[1] + 1
        self._seen = ""
        self._state: dict[str, Any] = {}
        self.publish()

    def now(self) -> int:
        """Unix ms."""
        return self.deps.clock_ms()

    def gate_for(self, log: Path, slug: str) -> PhaseGate:
        """A phase gate for one session's log (never ``PhaseGate.open``)."""
        return turns.gate_for(self, log, slug)

    def state(self) -> dict[str, Any]:
        """The published state (section 3)."""
        return self._state

    def chat_after(self, after: str | None) -> dict[str, dict[str, Any]]:
        """Chat lines after key `after` (all when None)."""
        session = self.session
        lines = {} if session is None else dict(session.chat)
        return {k: v for k, v in lines.items() if after is None or k > after}

    def _build(self) -> dict[str, Any]:
        session = self.session
        if session is None:
            return {
                "schema": 1,
                "step": None,
                "rung": None,
                "revealed": False,
                "chat_count": 0,
                "session": None,
                "steps": [],
            }
        events = session.events()
        derived = steps.derive(events)
        current = steps.open_step(derived)
        step = None if session.ended is not None or current is None else current.n
        state: dict[str, Any] = {
            "schema": 1,
            "step": step,
            "rung": steps.rung(events),
            "revealed": steps.revealed(events),
            "chat_count": len(session.chat),
            "session": session.info(),
            "steps": [steps.view(s, session.probe, session.probed_at) for s in derived],
        }
        if step == grading.TOOLBOX_STEP:
            state["toolbox"] = [
                {"name": e.name, "properties": list(e.properties)}
                for e in self.deps.box().entries
            ]
        return state

    def publish(self) -> None:
        """Rebuild the state; move ``rev`` and tell listeners if it changed."""
        with self.lock:
            body = self._build()
            seen = json.dumps(body, sort_keys=True)
            if seen == self._seen:
                return
            self._seen = seen
            self.rev += 1
            self._state = {**body, "rev": self.rev}
            if self.session is not None:
                save(self.live_path, self.session, self.rev)
            state, session = self._state, self.session
        for listener in self.listeners:
            listener(state, session)

    def live(self, sid: object) -> Session:
        """The live session `sid` names, or `not_live`."""
        session = self.session
        if session is None or session.ended is not None or session.sid != sid:
            msg = "That session is not the live one any more."
            raise CoachError(msg, code="not_live")
        return session

    def end(self, session: Session, reason: str) -> None:
        """Close `session` (it stays in the state, read-only)."""
        session.log_event("session_end", reason=reason, at=self.now())
        session.ended = self.now()
        session.end_reason = reason

    def _dispatch(self, req: protocol.Request) -> dict[str, Any]:
        body = req.body
        if req.kind == "session_start":
            return turns.start(self, req)
        session = self.live(body.get("session"))
        if req.kind == "session_end":
            self.end(session, "ended")
            return {}
        if req.kind == "grade_step":
            return grading.grade_step(self, session, body)
        if req.kind == "run_code":
            return turns.run_code(self, session, str(body["code"]))
        text = {"hint": "hint", "reveal": "reveal"}.get(req.kind, body.get("text"))
        return turns.chat(self, session, str(text))

    def handle(self, req: protocol.Request) -> dict[str, Any]:
        """Run one request; its result (section 2)."""
        with self.lock:
            self.chat.deadline = self.chat.monotonic() + REQUEST_CAP_S
            try:
                data = self._dispatch(req)
            except CoachError as exc:
                # An answer kuhy sees, not a crash; the journal says why too.
                _logger.warning("%s %s: %s (%s)", req.kind, req.rid, exc.code, exc)
                self.publish()
                return protocol.failure(
                    exc.code, str(exc), at=self.now(), retry=exc.retry, **exc.extra
                )
            self.publish()
            return protocol.ok(data, at=self.now(), state_rev=self.rev)

    def tick(self) -> None:
        """Probe for step 4's Accepted, at most once a minute, off the lock."""
        session = self.session
        if session is None or session.ended is not None:
            return
        current = steps.open_step(steps.derive(session.events()))
        if current is None or current.n != steps.IMPLEMENT:
            return
        if not self.deps.probe.due():
            return
        status = self.deps.probe.check(session.slug, session.started)
        with self.lock:
            if self.session is not session or session.ended is not None:
                return
            session.probe, session.probed_at = status, self.now()
            if status == ACCEPTED:
                at = self.now()
                event = {"step": 4, "grade": "pass", "attempt": 1, "forced": False}
                event |= {"via": "accepted", "feedback": "", "at": at}
                session.log_event("grade", **event)
                kind, text = grade_line(event)
                session.add("system", kind, text, at)
                session.notes.append(ACCEPTED_NOTE)
            self.publish()
