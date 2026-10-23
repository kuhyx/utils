"""The coaching chat: the CLI's sonnet session, one per problem.

The same session `leetcode_repl.run_claude` runs: it opens with
``/leetcode <slug>`` (which loads SKILL.md and arms the no-solution Stop
gate), then every turn is ``claude -p --resume``. Each call carries this
session's ``LEETCODE_COACH_LOG`` in the child's env only, so the Stop hook
reads the right log while one relay process serves every session.

On a usage limit the session continues on the local model with the history
so far, as the REPL hands over, and stays there. When that is down too the
turn fails ``claude_unavailable`` with the limit's reason and reset time.

Replies come back RAW: the caller strips and logs the rung marker
(`PhaseGate.after_reply`) after it has logged the turn's own events.
"""

from __future__ import annotations

import logging
import os
import re
from typing import TYPE_CHECKING, Any, Final
import urllib.error

from leetcode_coach import claude_cli, local_backend, local_cards, local_coach
from leetcode_coach.relay.errors import CoachError

if TYPE_CHECKING:
    from collections.abc import Callable

    from leetcode_coach.relay.session import Session

_logger: Final = logging.getLogger(__name__)

TURN_TIMEOUT_S: Final = 240.0
RESETS_RE: Final = re.compile(r"resets\s+([^\n]+?)\s*$", re.IGNORECASE | re.MULTILINE)
TurnError = CoachError
"""A coach turn produced no reply (``model_error`` / ``claude_unavailable``)."""


def model() -> str:
    """The coaching model (``LEETCODE_MODEL``, default sonnet, as the REPL)."""
    return os.environ.get("LEETCODE_MODEL") or "sonnet"


def _env(session: Session) -> dict[str, str]:
    env = {"LEETCODE_COACH_LOG": str(session.log)}
    if session.cluster:
        env["LEETCODE_COACH_CLUSTER"] = session.cluster
    return env


class CoachChat:
    """Runs turns for whichever session is live."""

    def __init__(
        self,
        ask: Callable[..., dict[str, Any]] = claude_cli.ask,
        local_chat: Callable[..., local_backend.LocalReply] = local_backend.chat,
    ) -> None:
        """Bind the claude call and the local model (both injectable)."""
        self._ask = ask
        self._local_chat = local_chat

    def _bounded(self, messages: list[dict[str, str]]) -> local_backend.LocalReply:
        return self._local_chat(messages, timeout=TURN_TIMEOUT_S)

    def open(self, session: Session) -> str:
        """The coach's opening reply for a fresh session."""
        return self._claude(session, "/leetcode " + session.slug, resume=False)

    def turn(self, session: Session, text: str) -> str:
        """Kuhy's `text` in, the coach's raw reply out."""
        if session.local:
            return self._local(session, text, reason=None)
        return self._claude(session, text, resume=True)

    def _claude(self, session: Session, text: str, *, resume: bool) -> str:
        args = ["--model", model()]
        if resume and session.claude_id:
            args += ["--resume", session.claude_id]
        reply = self._ask(args, text, timeout=TURN_TIMEOUT_S, env=_env(session))
        if claude_cli.is_limit_hit(reply):
            reason = str(reply.get("result") or "usage limit")
            _logger.warning("claude usage limit (%s): coaching on locally", reason)
            session.local = True
            return self._local(session, text, reason=reason)
        sid = reply.get("session_id")
        if reply.get("is_error") is True or not isinstance(sid, str) or not sid:
            _logger.warning("coach turn failed: %s", reply.get("_stderr") or reply)
            msg = "The coach did not answer; send it again."
            raise TurnError(msg, code="model_error", retry=True)
        session.claude_id = sid
        raw = str(reply.get("result", ""))
        session.history += [
            {"role": "user", "content": text},
            {"role": "assistant", "content": raw},
        ]
        return raw

    def _local(self, session: Session, text: str, *, reason: str | None) -> str:
        try:
            if session.local_coach is None:
                coach = local_coach.LocalCoach.start(
                    session.statement or session.slug, session.history
                )
                coach.chat = self._bounded
                coach.leak_guard = session.gate.leaks
                session.local_coach = coach
            turn = session.local_coach.respond(text)
        except (
            urllib.error.URLError,
            OSError,
            local_backend.ContextOverflowError,
        ) as exc:
            _logger.warning("local model could not answer either: %s", exc)
            why = reason or "claude usage limit"
            found = RESETS_RE.search(why)
            msg = "Claude is out of quota and the local model is down."
            raise TurnError(
                msg,
                code="claude_unavailable",
                reason=why,
                resets_at=found.group(1) if found else None,
            ) from exc
        display, _cards = local_cards.split_cards(turn.text)
        return display
