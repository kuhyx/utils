"""PreToolUse hook on Read: nudge to free-llm before reading a big shareable file.

Never blocks (editing a big file still needs a Read); only adds context when a
whole-file Read of a file over MIN_BYTES would pass the free-llm privacy gate.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from omniroute_offload import _privacy as privacy

MIN_BYTES = 60_000
NUDGE = (
    "{path} is {kb} KB (~{tokens}k tokens). If you only need to understand or "
    'summarize it (not edit it), run `free-llm -f {path} "<narrow question>"` '
    "(skill offload-free) and read only its answer; if a pattern suffices, grep it. "
    "Read it whole only if you must edit it or need exact text."
)


def nudge(payload: object) -> str | None:
    """Context to add for this tool call, or None to stay silent."""
    if not isinstance(payload, dict) or payload.get("tool_name") != "Read":
        return None
    tool_input = payload.get("tool_input")
    if (
        not isinstance(tool_input, dict)
        or "limit" in tool_input
        or "offset" in tool_input
    ):
        return None
    path = Path(str(tool_input.get("file_path", "")))
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size <= MIN_BYTES or privacy.file_refusal(path, home=Path.home()):
        return None
    return NUDGE.format(path=path, kb=size // 1000, tokens=size // 4000)


def main() -> int:
    """Read the hook JSON from stdin, print optional context JSON, always exit 0."""
    try:
        payload = json.loads(sys.stdin.read())
    except ValueError:
        return 0
    context = nudge(payload)
    if context:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "additionalContext": context,
                    }
                }
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
