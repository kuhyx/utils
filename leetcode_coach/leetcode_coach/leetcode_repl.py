#!/usr/bin/env python3
"""Coaching REPL for /leetcode that only ever shows the post-gate reply.

In the interactive TUI a Stop hook runs after the reply has streamed, so a
blocked reply (one that hands kuhy a pasteable line) is already on screen
before the rewrite appears. `claude -p` returns nothing until the hooks are
done, so this loop is the only client where the no-solution gate actually
withholds text from the human. Each turn is one `claude -p --resume` call.

Every block first passes the req-before-code phase gate (`phase.py`): code
sent before an accepted ``req:`` list is refused here and never reaches the
model. Replies lose their ``<!-- rung:Hn -->`` marker (logged) before printing.

When Claude answers with its usage-limit message (`claude_cli.is_limit_hit`)
the session continues on the local model (`local_session.py`) with the
conversation so far and the same gate; `--local` starts there.

Input: a block ends on an empty line (paste code, then press Enter twice).
`quit` or Ctrl-D leaves. `reveal` is passed through like any other message.
`leetcode report` prints the per-problem method report (`report.py`).
Started by the `leetcode` launcher as `python3 -m leetcode_coach.leetcode_repl`;
its prints ARE the session (T201 exemption in pyproject.toml).
"""

from __future__ import annotations

import functools
import logging
import os
import sys

from leetcode_coach import cluster_cli, local_session, phase, report
from leetcode_coach.claude_cli import ask, is_limit_hit

# Named, not __name__: under `-m` this module is `__main__`, which would escape
# the package logger's NullHandler and print the warning to the session.
_LOG = logging.getLogger("leetcode_coach.leetcode_repl")


def read_block() -> str | None:
    """Lines until an empty one; None on EOF with nothing typed."""
    print("\nyou> ", end="", flush=True)
    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            # Ctrl-D is how kuhy leaves; benign, logged only to satisfy the
            # repo's no-silent-except rule (the package logger is silent).
            _LOG.warning("stdin closed (Ctrl-D); ending the block")
            return "\n".join(lines) if lines else None
        if not line.strip():
            if lines:
                return "\n".join(lines)
            continue
        lines.append(line)


def _screen(gate: phase.PhaseGate, block: str) -> str | None:
    """The block to send the coach, or None when the phase gate refuses it."""
    sent, note = gate.screen(block)
    if note:
        print(note)
    return sent


def run_claude(model: str, problem: list[str]) -> int:
    """The Claude session; hands over to the local model on a usage limit."""
    gate = phase.PhaseGate.open(problem[0])
    opener = local_session.opening_message(problem[1:])
    first = ask(["--model", model], "/leetcode " + " ".join(problem))
    if is_limit_hit(first):
        print(f"[{first.get('result', 'usage limit')} -- switching to local model]")
        return local_session.run(problem[0], [], opener, read_block, gate=gate)
    session = first.get("session_id")
    print(gate.after_reply(str(first.get("result", ""))))
    if not session:
        return 1
    history = [
        {"role": "user", "content": opener},
        {"role": "assistant", "content": str(first.get("result", ""))},
    ]
    while True:
        block = read_block()
        if block is None or local_session.is_quit(block):
            return 0
        if (sent := _screen(gate, block)) is None:
            continue
        print("\n...", flush=True)
        reply = ask(["--model", model, "--resume", session], sent)
        if is_limit_hit(reply):
            print(f"[{reply.get('result', 'usage limit')} -- continuing locally]")
            return local_session.run(problem[0], history, sent, read_block, gate=gate)
        print(gate.after_reply(str(reply.get("result", ""))))
        history += [
            {"role": "user", "content": sent},
            {"role": "assistant", "content": str(reply.get("result", ""))},
        ]


def start_session(problem: list[str], *, local: bool) -> int:
    """One coaching session for `<url-or-slug> [stuck on...]`."""
    if local:
        opener = local_session.opening_message(problem[1:])
        gate = phase.PhaseGate.open(problem[0])
        return local_session.run(problem[0], [], opener, read_block, gate=gate)
    return run_claude(os.environ.get("LEETCODE_MODEL", "sonnet"), problem)


def main(argv: list[str]) -> int:
    """Parse `[--local] <url-or-slug> [stuck on...]` (or `report`) and run it."""
    local = "--local" in argv
    args = [a for a in argv if a != "--local"]
    if args[:1] == [report.COMMAND]:
        return report.main(args[1:])
    if not args or args[0] in {"-h", "--help"}:
        print("Usage: leetcode [--local] <url-or-slug> [what you are stuck on...]")
        print("  LEETCODE_MODEL=opus leetcode ...     to use a stronger model")
        print("  --local   coach on the local Ollama model (free, offline)")
        print("  leetcode due | --cluster <name> | --retest <slug>   (--dry-run)")
        print("  leetcode report   req-before-code, max rung, reveal per problem")
        return 0
    if args[0] in cluster_cli.COMMANDS:
        return cluster_cli.main(args, functools.partial(start_session, local=local))
    return start_session(args, local=local)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
