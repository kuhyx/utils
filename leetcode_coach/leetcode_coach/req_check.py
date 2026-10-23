"""Judge kuhy's requirement list, and ambiguous code, on a cheap model.

TODO-coach.md decision 5: a separate ``claude -p --model haiku`` call (the
coaching session stays on sonnet), Ollama through `local_backend` when haiku
is out of quota, errors or answers something that is not the JSON asked for,
and when neither answers the gate fails OPEN: ``unverified``, kuhy continues.

The checker may only name *missing properties* from the toolbox vocabulary.
That is enforced here, not trusted to the prompt: every ``missing`` item that
is not a vocabulary key is dropped (an entry name like "XOR" is a leak, and an
invented property is noise). An ``incomplete`` whose every item was dropped
names nothing kuhy could fix, so it counts as no answer and falls through.

The haiku call runs with no tools, no MCP, no hooks and no session file: the
global CLAUDE.md still loads (no OAuth-compatible way to skip it), which is
why the answer is extracted and validated rather than parsed whole.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from typing import TYPE_CHECKING, Any
import urllib.error

from leetcode_coach import claude_cli, local_backend

if TYPE_CHECKING:
    from collections.abc import Callable

    from leetcode_coach.toolbox import Toolbox

_LOG = logging.getLogger(__name__)

HAIKU_TIMEOUT_S = 50.0
LOCAL_TIMEOUT_S = 200.0
"""Ollama's share of a check: with haiku's 50 s it fits the relay's 280 s cap."""
HAIKU_ARGS = [
    "--model",
    "haiku",
    "--tools",
    "",
    "--strict-mcp-config",
    "--no-session-persistence",
    "--disable-slash-commands",
    "--settings",
    '{"disableAllHooks": true}',
]
CHECK_SYSTEM = (
    "You check a student's requirement list for a programming problem. You are "
    "given the problem, the list, and a vocabulary of properties an operation "
    "can have. Decide which vocabulary properties the operation that solves "
    "the problem must have, and whether the list states each of them in any "
    "words. Reply with ONE JSON object and nothing else: "
    '{"verdict": "pass" | "incomplete", "missing": [<vocabulary property names>]}. '
    "Never name an operation, a data structure or an algorithm; only the "
    "property names from the vocabulary may appear in missing."
)
CODE_SYSTEM = (
    "You decide whether a chat message is program source code (a line or "
    "block someone would paste into a solution) or prose (a question or an "
    'idea, even one that mentions a symbol). Reply with ONE JSON object: {"code": '
    'true} or {"code": false}.'
)


@dataclass(frozen=True)
class Check:
    """A checker answer: verdict, the missing properties, and who answered."""

    verdict: str
    missing: tuple[str, ...] = ()
    via: str = "none"


def extract_json(text: str) -> dict[str, Any] | None:
    """The JSON object starting at the first ``{`` (fences and chatter ignored)."""
    start = text.find("{")
    if start == -1:
        return None
    try:
        obj, _end = json.JSONDecoder().raw_decode(text, start)
    except ValueError as exc:
        _LOG.warning("checker answer is not a JSON object: %s", exc)
        return None
    return obj if isinstance(obj, dict) else None


def parse_verdict(obj: object, vocabulary: dict[str, str]) -> Check | None:
    """A validated verdict, or None when the answer is unusable."""
    if not isinstance(obj, dict) or obj.get("verdict") not in {"pass", "incomplete"}:
        return None
    missing = obj.get("missing", [])
    if not isinstance(missing, list):
        return None
    kept = tuple(m for m in missing if isinstance(m, str) and m in vocabulary)
    if obj["verdict"] == "pass":
        return Check("pass")
    return Check("incomplete", kept) if kept else None


def check_prompt(statement: str, req: str, box: Toolbox) -> str:
    """The checker's user message: problem, list, vocabulary, toolbox."""
    vocab = "\n".join(
        f"- {name}: {meaning}" for name, meaning in box.properties.items()
    )
    toolbox = "\n".join(
        f"- {', '.join(e.properties)}" for e in box.entries if e.properties
    )
    return (
        f"## Problem\n{statement.strip()}\n\n## Requirement list\n{req.strip()}\n\n"
        f"## Property vocabulary\n{vocab}\n\n"
        f"## Property sets the known operations offer\n{toolbox}\n"
    )


def ask_models[T](
    system: str,
    prompt: str,
    validate: Callable[[dict[str, Any] | None], T | None],
    ask: Callable[..., dict[str, Any]] | None,
) -> tuple[T, str] | None:
    """Haiku, then Ollama; the first validated answer and who gave it."""
    asker = claude_cli.ask if ask is None else ask
    reply = asker(
        [*HAIKU_ARGS, "--system-prompt", system], prompt, timeout=HAIKU_TIMEOUT_S
    )
    if not claude_cli.is_limit_hit(reply):
        got = validate(extract_json(str(reply.get("result", ""))))
        if got is not None:
            return got, "haiku"
    try:
        local = local_backend.chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            timeout=LOCAL_TIMEOUT_S,
        )
    except (urllib.error.URLError, OSError, local_backend.ContextOverflowError) as exc:
        _LOG.warning("Ollama could not answer the check either: %s", exc)
        return None
    got = validate(extract_json(local.text))
    return None if got is None else (got, "ollama")


def check(
    statement: str,
    req: str,
    box: Toolbox,
    ask: Callable[..., dict[str, Any]] | None = None,
) -> Check:
    """Judge `req` against the problem; ``unverified`` when nobody can."""
    if not box.properties:
        _LOG.warning("no property vocabulary: the req list stays unverified")
        return Check("unverified")
    got = ask_models(
        CHECK_SYSTEM,
        check_prompt(statement, req, box),
        lambda obj: parse_verdict(obj, box.properties),
        ask,
    )
    if got is None:
        return Check("unverified")
    verdict, via = got
    return Check(verdict.verdict, verdict.missing, via)


def _code_flag(obj: dict[str, Any] | None) -> bool | None:
    flag = None if obj is None else obj.get("code")
    return flag if isinstance(flag, bool) else None


def looks_like_code(
    block: str, ask: Callable[..., dict[str, Any]] | None = None
) -> bool:
    """The model's call on a block the regex could not decide; prose if unsure."""
    got = ask_models(CODE_SYSTEM, block, _code_flag, ask)
    return False if got is None else got[0]
