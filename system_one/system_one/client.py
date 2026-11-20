"""Loopback-only client for the TypeSafe System One API (``POST /v1/systemone``).

Speaks the request shape Jev defined and Kev (``jaredpalmer/kev``) serves
locally. It refuses any non-loopback base URL: the whole point of the local
setup is that a decision never leaves the machine and never costs money, so a
misconfigured URL must fail closed instead of quietly calling a paid endpoint.
"""

from __future__ import annotations

import ipaddress
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

DEFAULT_BASE_URL = "http://127.0.0.1:8008/v1"
DEFAULT_TIMEOUT_S = 30.0

Questions = dict[str, dict[str, Any]]


class SystemOneError(RuntimeError):
    """A request failed, timed out or was refused before it was sent."""


@dataclass(frozen=True)
class Decision:
    """One answered request: the per-question answers plus wall time."""

    answers: dict[str, dict[str, Any]]
    wall_ms: int
    raw: dict[str, Any]


def require_loopback(base_url: str) -> str:
    """Return ``base_url`` unchanged if it points at this machine, else raise.

    Args:
        base_url: e.g. ``http://127.0.0.1:8008/v1``.

    Returns:
        The same URL.

    Raises:
        SystemOneError: for any host that is not localhost / a loopback IP.
    """
    host = urllib.parse.urlsplit(base_url).hostname or ""
    if host == "localhost":
        return base_url
    try:
        if ipaddress.ip_address(host).is_loopback:
            return base_url
    except ValueError:
        pass
    msg = (
        f"refusing non-loopback System One endpoint {host!r} (local-only, no paid APIs)"
    )
    raise SystemOneError(msg)


def noul(instructions: str) -> dict[str, Any]:
    """A yes/no question."""
    return {"type": "noul", "instructions": instructions}


def choice(instructions: str, options: dict[str, str]) -> dict[str, Any]:
    """A pick-one question; ``options`` maps option name to description."""
    return {"type": "choice", "instructions": instructions, "criteria": options}


def score(instructions: str, levels: list[str]) -> dict[str, Any]:
    """An ordered rating question; ``levels`` lowest first."""
    return {"type": "score", "instructions": instructions, "criteria": levels}


def decide(
    state: str,
    questions: Questions,
    *,
    base_url: str = DEFAULT_BASE_URL,
    model: str = "kev-latest",
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> Decision:
    """Ask every question about ``state`` in one request.

    Args:
        state: The text the questions are about.
        questions: Question id -> question (see :func:`noul` etc.).
        base_url: Loopback base URL; ``/systemone`` is appended.
        model: Model id sent in the request (Kev ignores unknown ids).
        timeout_s: Socket timeout for the whole request.

    Returns:
        The decision.

    Raises:
        SystemOneError: refused URL, HTTP error, timeout or malformed reply.
    """
    url = require_loopback(base_url).rstrip("/") + "/systemone"
    body = json.dumps({"state": state, "model": model, "questions": questions})
    req = urllib.request.Request(
        url,
        data=body.encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer local"},
        method="POST",
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw: dict[str, Any] = json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        msg = f"System One request failed: {exc}"
        raise SystemOneError(msg) from exc
    answers = raw.get("answers")
    if not isinstance(answers, dict) or set(answers) != set(questions):
        msg = f"malformed System One reply: {str(raw)[:200]}"
        raise SystemOneError(msg)
    return Decision(answers, int((time.monotonic() - t0) * 1000), raw)
