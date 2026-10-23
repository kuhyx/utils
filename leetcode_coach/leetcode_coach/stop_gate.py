"""Stop hook: in a /leetcode session, refuse a reply that hands kuhy a line of code.

Before kuhy's first code it also bounces a reply that names a toolbox entry
(`leak`), except an entry kuhy or the fetched problem already named.

The prose rule ("never write a line for their code") held in one haiku
role-play out of two, so it is adjudicated here instead. A reply is blocked
when any code span or fenced block in it uses an identifier from the
problem's starter signature (e.g. `fn`, `args`) together with a call/spread/
assignment -- unless that exact snippet already appears in one of kuhy's own
messages (quoting their code back is fine). `reveal` lifts the gate.

Blocking returns {"decision": "block"} so the model rewrites the reply; the
rewrite is judged again, at most MAX_BLOCKS times per prompt (counted in
~/.claude/state/leetcode/<session>.blocks), then the gate fails open.

Run as ``/usr/bin/python3 -P -m leetcode_coach.stop_gate``; the file in
``~/.claude/hooks`` is a shim that execs exactly that. The printed JSON line
IS the hook's interface (hence the T201 exemption in pyproject.toml).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys

from leetcode_coach import (
    gate_detector,
    leak,
    local_prompt,
    phase,
    session_log,
    toolbox,
)

SKILL_LINK = Path.home() / ".claude" / "skills" / "leetcode"
# A /leetcode slash command, or a model-invoked Skill(leetcode) load (which
# leetcode_url_userprompt.sh triggers when kuhy pastes a bare problem URL).
# The skill directory is a symlink to this package since 2026-10-23, and the
# harness may print either side of it as the base directory: both arm.
MARKERS = (
    (
        '"content":"<command-message>leetcode</command-message>'
        "\\n<command-name>/leetcode</command-name>"
    ),
    f'"text":"Base directory for this skill: {SKILL_LINK}',
    f'"text":"Base directory for this skill: {Path(__file__).resolve().parent}',
)
STATE_DIR = Path.home() / ".claude" / "state" / "leetcode"
MAX_BLOCKS = 2  # rewrites per prompt before the gate lets the reply through


def verdict(raw: str, reply: str) -> str | None:
    """Reason to block `reply`, or None when it may stand."""
    if not reply or not any(m in raw for m in MARKERS):
        return None
    entries = gate_detector.transcript_lines(raw)
    users = [gate_detector.kuhy_text(e) for e in entries if e.get("type") == "user"]
    if any(u.strip() == "reveal" for u in users):
        return None
    if not _code_seen(users):
        quoted = [gate_detector.allowed_text(entries)]
        named = leak.leaked_names(reply, quoted, toolbox.load_safe())
        if named:
            return local_prompt.GATE_REASON_LEAK.format(names=", ".join(named))
    idents = gate_detector.starter_identifiers(entries)
    if not idents:
        return None
    allowed = gate_detector.allowed_text(entries)
    bad = gate_detector.offending_snippets(reply, idents, allowed)
    if not bad:
        return None
    return (
        "leetcode gate: your reply hands kuhy code they can paste \u2014 "
        + "; ".join(f"`{b}`" for b in bad)
        + ". Rewrite it without that snippet: describe the data or name the "
        "construct, and keep the one question at the end."
    )


def _code_seen(users: list[str]) -> bool:
    """Whether kuhy's code has reached the coach: the REPL's log says so.

    The REPL exports the log path (`session_log.LOG_ENV`). The TUI has no REPL
    and no log, so there a code block among kuhy's own turns stands in for the
    ``code`` event (regex only: a hook must not wait on a model).
    """
    log = os.environ.get(session_log.LOG_ENV)
    if log:
        return session_log.has_code(Path(log))
    return any(phase.regex_verdict(u.strip()) is True for u in users)


def blocks_so_far(session_id: str, prompt_id: str) -> int:
    """How many times this prompt's reply was already sent back.

    Bounded so a model that cannot satisfy the gate still gets to answer
    (fail-open at the cap).
    """
    state = STATE_DIR / f"{session_id}.blocks"
    entries = state.read_text(encoding="utf-8").split() if state.is_file() else []
    n = entries.count(prompt_id)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with state.open("a", encoding="utf-8") as fh:
        fh.write(prompt_id + "\n")
    return n


def main() -> int:
    """Judge the reply in the Stop event on stdin; print a block decision or nothing."""
    data = json.load(sys.stdin)
    path = Path(data.get("transcript_path", ""))
    if not path.is_file():
        return 0
    # The transcript on disk still lacks the reply being judged; the harness
    # hands it over separately (measured: `last_assistant_message`, 2.1.276).
    reply = str(data.get("last_assistant_message") or "")
    reason = verdict(path.read_text(encoding="utf-8", errors="replace"), reply)
    if not reason:
        return 0
    if (
        blocks_so_far(str(data.get("session_id")), str(data.get("prompt_id")))
        >= MAX_BLOCKS
    ):
        return 0
    print(json.dumps({"decision": "block", "reason": reason}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
