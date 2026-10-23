"""The one `claude -p` call, shared by the coaching REPL and the req checker.

The binary is looked up per call (``LEETCODE_CLAUDE_BIN``, else PATH), so the
E2E tests can point a running REPL at a fake. A binary that cannot start or
hangs past `timeout` comes back as an error reply, never an exception: the
checker treats it as "haiku did not answer" and falls back.

The signal for a spent plan is the synthetic reply "You've hit your session
limit · resets 3pm (Europe/Warsaw)" (error rate_limit, HTTP 429), as recorded
in real transcripts on 2026-09-26.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

_LOG = logging.getLogger(__name__)

LIMIT_RE = re.compile(r"hit your (?:\w+ )?limit|usage limit reached", re.IGNORECASE)
RATE_LIMIT_STATUS = 429


def claude_bin() -> str:
    """``LEETCODE_CLAUDE_BIN``, else ``claude`` from PATH.

    PATH lookup, not a fixed path: claude lives in ~/.local/bin here, and the
    old /usr/bin/claude default made every REPL turn crash (2026-10-20).
    """
    return os.environ.get("LEETCODE_CLAUDE_BIN") or shutil.which("claude") or "claude"


def ask(
    args: list[str], prompt: str, *, timeout: float | None = None
) -> dict[str, Any]:
    """One `claude -p` turn; the JSON result, or a stand-in carrying stderr."""
    env = {**os.environ, "CLAUDE_TTY_FIX_OFF": "1"}
    try:
        proc = subprocess.run(
            [claude_bin(), "-p", *args, "--output-format", "json", prompt],
            capture_output=True,
            stdin=subprocess.DEVNULL,  # claude -p would otherwise drain REPL input
            text=True,
            env=env,
            check=False,
            cwd=Path.home(),
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        _LOG.warning("claude -p could not run: %s", exc)
        return {"result": f"[claude could not run: {exc}]", "_stderr": str(exc)}
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
