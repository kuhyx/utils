"""The offline /leetcode coach: SKILL.md rules, the no-solution gate, cards.

Claude Code enforces the gate as a Stop hook; there is no harness here, so the
same detector (`gate_detector`, which the Stop hook also uses) runs on every
local reply before it is shown. A blocked reply is sent back with the gate's
reason, like the hook's `{"decision": "block"}`, and after `MAX_TRIES` failed
drafts a fixed safe message is shown instead -- unlike the hook, which fails
open, because a small local model is likelier to keep leaking.

The model has no tools: the statement is prefetched into the system prompt,
and cards come back as a ```cards block (`local_cards.py`). "End with exactly
one task" is checked here too, as a soft gate: a reply that fails only that is
regenerated, and after `MAX_TRIES` the last code-free draft is shown anyway.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from leetcode_coach import gate_detector, local_backend, local_cards, local_prompt

if TYPE_CHECKING:
    from collections.abc import Callable

SKILL_DIR = Path(__file__).resolve().parent
MAX_TRIES = 3


def gate_findings(reply: str, statement: str, user_texts: list[str]) -> list[str]:
    """Snippets in `reply` the hook would block, judged on synthetic entries."""
    if any(t.strip() == "reveal" for t in user_texts):
        return []
    entries = [
        {"type": "user", "message": {"content": text}}
        for text in [statement, *user_texts]
    ]
    idents = gate_detector.starter_identifiers(entries)
    if not idents:
        return []
    allowed = gate_detector.allowed_text(entries)
    return list(gate_detector.offending_snippets(reply, idents, allowed))


@dataclass
class Turn:
    """What one user message produced."""

    text: str
    seconds: float
    attempts: int
    withheld: bool


@dataclass
class LocalCoach:
    """A local coaching conversation, gate applied to every reply."""

    statement: str
    history: list[dict[str, str]]
    chat: Callable[[list[dict[str, str]]], local_backend.LocalReply] = (
        local_backend.chat
    )
    leak_guard: Callable[[str, list[str]], list[str]] | None = None
    """Toolbox entries a draft names too early (`PhaseGate.leaks`); off if None."""

    @classmethod
    def start(
        cls, statement: str, history: list[dict[str, str]] | None = None
    ) -> LocalCoach:
        """A coach seeded with SKILL.md and optionally a prior (Claude) history."""
        skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        prompt = local_prompt.system_prompt(skill, statement)
        system = {"role": "system", "content": prompt}
        return cls(statement=statement, history=[system, *(history or [])])

    def user_texts(self) -> list[str]:
        """Everything kuhy typed so far."""
        return [m["content"] for m in self.history if m["role"] == "user"]

    @staticmethod
    def _with_reminder(history: list[dict[str, str]]) -> list[dict[str, str]]:
        """`history` with `REMINDER` on its last message (a copy; history is kept)."""
        last = history[-1]
        reminded = {**last, "content": last["content"] + local_prompt.REMINDER}
        return [*history[:-1], reminded]

    def respond(self, text: str) -> Turn:
        """Append kuhy's message and return the first reply that passes the gate."""
        self.history.append({"role": "user", "content": text})
        scratch: list[dict[str, str]] = []
        total = 0.0
        last_clean: str | None = None
        for attempt in range(1, MAX_TRIES + 1):
            reply = self.chat(self._with_reminder(self.history) + scratch)
            total += reply.seconds
            display, payload = local_cards.split_cards(reply.text)
            bad = gate_findings(display, self.statement, self.user_texts())
            named = self._leaks(display) if not bad else []
            if bad:
                snippets = "; ".join(f"`{b}`" for b in bad)
                reason = local_prompt.GATE_REASON_CODE.format(snippets=snippets)
            elif named:
                reason = local_prompt.GATE_REASON_LEAK.format(names=", ".join(named))
            else:
                last_clean = reply.text
                prose, _rung = local_prompt.split_rung(display)
                if payload is not None or local_prompt.ends_with_one_task(prose):
                    return self._accept(reply.text, total, attempt)
                reason = local_prompt.GATE_REASON_SHAPE
            scratch += [
                {"role": "assistant", "content": reply.text},
                {"role": "user", "content": reason},
            ]
        if last_clean is not None:  # shape is a soft rule; code is the hard one
            return self._accept(last_clean, total, MAX_TRIES)
        self.history.append({"role": "assistant", "content": local_prompt.WITHHELD})
        return Turn(local_prompt.WITHHELD, total, MAX_TRIES, withheld=True)

    def _leaks(self, display: str) -> list[str]:
        """Entry names the draft gives away, per the session's leak guard."""
        if self.leak_guard is None:
            return []
        return self.leak_guard(display, self.user_texts())

    def _accept(self, text: str, seconds: float, attempts: int) -> Turn:
        """Record `text` as the assistant's reply and wrap it as a Turn."""
        self.history.append({"role": "assistant", "content": text})
        return Turn(text, seconds, attempts, withheld=False)
