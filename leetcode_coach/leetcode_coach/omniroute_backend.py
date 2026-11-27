"""OmniRoute transport for the /leetcode coach: the free models, after Claude.

When Claude reports a usage limit the coach goes on with OmniRoute's
``free-best`` chain (kuhy 2026-11-27), and with Ollama only if the gateway is
down (``free_chain``). One non-streaming OpenAI ``/v1/chat/completions`` call
per reply, so the no-solution gate in ``local_coach`` judges the whole draft
before anything reaches the screen, exactly as for Ollama.

The gateway is local (docker ``omniroute`` on 127.0.0.1:20128); a non-loopback
URL is refused. The free providers behind it log prompts: the coach's prompts
carry the problem and kuhy's attempts and nothing else (kuhy accepted that).
An empty answer (``content: null`` from a reasoning member, an empty choice
list) is a :class:`GatewayError`, so the chain falls through instead of
showing nothing.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import time
from typing import TYPE_CHECKING, Any, Final
import urllib.parse
import urllib.request

from leetcode_coach import local_backend

if TYPE_CHECKING:
    from collections.abc import Callable

DEFAULT_URL: Final = "http://127.0.0.1:20128"
URL_ENV: Final = "LEETCODE_OMNIROUTE_URL"
"""Overrides :data:`DEFAULT_URL` (a test's fake gateway, a dead port)."""
KEY_FILE = Path.home() / ".config" / "omniroute" / "api_key"
MODEL: Final = "free-best"
MAX_TOKENS: Final = 4000
"""Reasoning members spend small budgets on thinking and return nothing."""
CONTEXT_TOKENS: Final = 32768
"""The combo's prompt limit; a longer prompt would be cut silently."""
TEMPERATURE: Final = 0.4
REQUEST_TIMEOUT_S: Final = 120.0
_LOOPBACK: Final = frozenset({"127.0.0.1", "localhost", "::1"})


class GatewayError(ConnectionError):
    """The gateway answered nothing usable; the chain moves to the next rung."""


def gateway_url() -> str:
    """The gateway base URL, read at call time."""
    return os.environ.get(URL_ENV) or DEFAULT_URL


def read_key(path: Path | None = None) -> str:
    """The gateway's Bearer key (never printed)."""
    try:
        return (path or KEY_FILE).read_text(encoding="utf-8").strip()
    except OSError as exc:
        msg = f"OmniRoute key unreadable: {exc}"
        raise GatewayError(msg) from exc


def http_json(
    url: str,
    payload: dict[str, Any],
    timeout: float,
    *,
    key_file: Path | None = None,
) -> dict[str, Any]:
    """POST ``payload`` with the Bearer key to the local gateway; decode the JSON."""
    host = urllib.parse.urlsplit(url).hostname or ""
    if not url.startswith("http://") or host not in _LOOPBACK:
        msg = f"refusing a non-loopback gateway URL: {url}"
        raise ValueError(msg)
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {read_key(key_file)}",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        answer: dict[str, Any] = json.loads(resp.read().decode())
    return answer


def _content(data: dict[str, Any]) -> str:
    """The first choice's text, or ``""``."""
    choices = data.get("choices") or [{}]
    message = choices[0].get("message") or {}
    return str(message.get("content") or "")


def chat(
    messages: list[dict[str, str]],
    *,
    post: Callable[[str, dict[str, Any], float], dict[str, Any]] = http_json,
    clock: Callable[[], float] = time.monotonic,
    timeout: float = REQUEST_TIMEOUT_S,
) -> local_backend.LocalReply:
    """Ask ``free-best`` for the next assistant message.

    Raises:
        ContextOverflowError: the prompt would not fit the combo's limit.
        GatewayError: the gateway answered no text.
    """
    if local_backend.estimate_tokens(messages) >= CONTEXT_TOKENS:
        msg = f"conversation too long for the gateway ({CONTEXT_TOKENS} tokens)"
        raise local_backend.ContextOverflowError(msg)
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "max_tokens": MAX_TOKENS,
        "temperature": TEMPERATURE,
    }
    start = clock()
    data = post(f"{gateway_url()}/v1/chat/completions", payload, timeout)
    text = local_backend.strip_think(_content(data))
    if not text:
        msg = f"{MODEL} answered no text"
        raise GatewayError(msg)
    return local_backend.LocalReply(
        text=text,
        seconds=clock() - start,
        prompt_tokens=int((data.get("usage") or {}).get("prompt_tokens") or 0),
        via="omniroute",
        model=str(data.get("model") or MODEL),
    )
