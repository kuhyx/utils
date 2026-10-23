"""Post-mortem cards from a local reply: extract the ```cards block, build the deck.

The local model has no tools, so instead of the Bash call SKILL.md describes it
emits the JSON in a fenced ```cards block; this module lifts it out of the
displayed text and pipes it to `make_cards`, whose validation is unchanged.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

_LOG = logging.getLogger(__name__)

CARDS_RE = re.compile(r"```cards\s*\n(.*?)```", re.DOTALL)


def split_cards(reply: str) -> tuple[str, dict[str, Any] | None]:
    """Remove a ```cards block from `reply`; return (display text, parsed JSON)."""
    match = CARDS_RE.search(reply)
    if match is None:
        return reply, None
    display = (reply[: match.start()] + reply[match.end() :]).strip()
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        _LOG.warning("the cards block is not JSON: %s", exc)
        return display, {"invalid": match.group(1)}
    return display, payload if isinstance(payload, dict) else {"invalid": payload}


def deliver_cards(
    payload: dict[str, Any],
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> tuple[bool, str]:
    """Pipe the cards to the card builder; (accepted, its stdout+stderr)."""
    if "invalid" in payload:
        return False, f"cards block is not a JSON object: {payload['invalid']!r}"
    proc = run(
        [sys.executable, "-m", "leetcode_coach.make_cards", "-"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0, (proc.stdout + proc.stderr).strip()
