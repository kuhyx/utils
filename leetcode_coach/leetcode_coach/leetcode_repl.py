#!/usr/bin/env python3
"""Coaching REPL for /leetcode that only ever shows the post-gate reply.

In the interactive TUI a Stop hook runs after the reply has streamed, so a
blocked reply (one that hands kuhy a pasteable line) is already on screen
before the rewrite appears. `claude -p` returns nothing until the hooks are
done, so this loop is the only client where the no-solution gate actually
withholds text from the human. Each turn is one `claude -p --resume` call.

When Claude answers with its usage-limit message the session continues on the
local model (`local_session.py`) with the conversation so far; `--local` starts
there. The signal is the synthetic reply "You've hit your session limit ·
resets 3pm (Europe/Warsaw)" (error rate_limit, HTTP 429), as recorded in real
transcripts on 2026-09-26.

Input: a block ends on an empty line (paste code, then press Enter twice).
`quit` or Ctrl-D leaves. `reveal` is passed through like any other message.
Started by the `leetcode` launcher as `python3 -m leetcode_coach.leetcode_repl`;
its prints ARE the session (T201 exemption in pyproject.toml).
"""

from __future__ import annotations

import functools
import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

from leetcode_coach import cluster_cli, local_session

# Named, not __name__: under `-m` this module is `__main__`, which would escape
# the package logger's NullHandler and print the warning to the session.
_LOG = logging.getLogger("leetcode_coach.leetcode_repl")

# PATH lookup, not a fixed path: claude lives in ~/.local/bin here, and the
# old /usr/bin/claude default made every REPL turn crash (2026-10-20).
CLAUDE = os.environ.get("LEETCODE_CLAUDE_BIN") or shutil.which("claude") or "claude"
LIMIT_RE = re.compile(r"hit your (?:\w+ )?limit|usage limit reached", re.IGNORECASE)
RATE_LIMIT_STATUS = 429


def ask(args: list[str], prompt: str) -> dict[str, Any]:
    """One `claude -p` turn; the JSON result, or a stand-in carrying stderr."""
    env = {**os.environ, "CLAUDE_TTY_FIX_OFF": "1"}
    proc = subprocess.run(
        [CLAUDE, "-p", *args, "--output-format", "json", prompt],
        capture_output=True,
        stdin=subprocess.DEVNULL,  # claude -p would otherwise drain our REPL input
        text=True,
        env=env,
        check=False,
        cwd=Path.home(),
    )
    reply: object
    try:
        reply = json.loads(proc.stdout, strict=False) if proc.stdout.strip() else {}
    except json.JSONDecodeError as exc:
        _LOG.warning("claude -p printed something that is not JSON: %s", exc)
        reply = {}
    result: dict[str, Any] = reply if isinstance(reply, dict) else {}
    result["_stderr"] = proc.stderr.strip()
    if proc.returncode != 0 and "result" not in result:
        result["result"] = f"[claude exited {proc.returncode}]\n{proc.stderr.strip()}"
    return result


def is_limit_hit(reply: dict[str, Any]) -> bool:
    """Whether Claude refused this turn because the plan's usage limit is spent."""
    if reply.get("api_error_status") == RATE_LIMIT_STATUS:
        return True
    text = f"{reply.get('result', '')}\n{reply.get('_stderr', '')}"
    return bool(LIMIT_RE.search(text))


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


def run_claude(model: str, problem: list[str]) -> int:
    """The Claude session; hands over to the local model on a usage limit."""
    opener = local_session.opening_message(problem[1:])
    first = ask(["--model", model], "/leetcode " + " ".join(problem))
    if is_limit_hit(first):
        print(f"[{first.get('result', 'usage limit')} -- switching to local model]")
        return local_session.run(problem[0], [], opener, read_block)
    session = first.get("session_id")
    print(first.get("result", ""))
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
        print("\n...", flush=True)
        reply = ask(["--model", model, "--resume", session], block)
        if is_limit_hit(reply):
            print(f"[{reply.get('result', 'usage limit')} -- continuing locally]")
            return local_session.run(problem[0], history, block, read_block)
        print(reply.get("result", ""))
        history += [
            {"role": "user", "content": block},
            {"role": "assistant", "content": str(reply.get("result", ""))},
        ]


def start_session(problem: list[str], *, local: bool) -> int:
    """One coaching session for `<url-or-slug> [stuck on...]`."""
    if local:
        opener = local_session.opening_message(problem[1:])
        return local_session.run(problem[0], [], opener, read_block)
    return run_claude(os.environ.get("LEETCODE_MODEL", "sonnet"), problem)


def main(argv: list[str]) -> int:
    """Parse `[--local] <url-or-slug> [stuck on...]` and run a session."""
    local = "--local" in argv
    args = [a for a in argv if a != "--local"]
    if not args or args[0] in {"-h", "--help"}:
        print("Usage: leetcode [--local] <url-or-slug> [what you are stuck on...]")
        print("  LEETCODE_MODEL=opus leetcode ...     to use a stronger model")
        print("  --local   coach on the local Ollama model (free, offline)")
        print("  leetcode due | --cluster <name> | --retest <slug>   (--dry-run)")
        return 0
    if args[0] in cluster_cli.COMMANDS:
        return cluster_cli.main(args, functools.partial(start_session, local=local))
    return start_session(args, local=local)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
