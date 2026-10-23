"""Ollama transport for the offline /leetcode coach.

One non-streaming `/api/chat` call per reply, so the no-solution gate can judge
the whole reply before anything reaches the screen -- the same reason the
Claude path uses `claude -p`. Thinking is switched off (`think: false`) and any
`<think>` block that leaks anyway is stripped before the gate sees the text.

Ollama silently truncates a prompt longer than `num_ctx` from the front, which
would drop the system prompt (the coaching rules) without an error. So the
context is set explicitly and both the client-side estimate and the server's
`prompt_eval_count` are checked against it.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
import subprocess
import time
from typing import TYPE_CHECKING, Any
import urllib.request

if TYPE_CHECKING:
    from collections.abc import Callable

OLLAMA_URL = "http://localhost:11434"
# The instruct build, not plain `qwen3:30b-a3b`: that tag is the 2507 Thinking
# build, which ignores `think: false` and `/no_think` and writes ~1k tokens of
# reasoning into `content` before every reply (measured 2026-10-03: 66 s turns).
MODEL = "qwen3:30b-a3b-instruct-2507-q4_K_M"
NUM_CTX = 16384
KEEP_ALIVE = "5m"  # free the 3090 soon after a session ends
TEMPERATURE = 0.4
REQUEST_TIMEOUT_S = 300.0  # the first call also loads ~18 GB into VRAM
CHARS_PER_TOKEN = 3.0  # pessimistic, so the estimate trips before Ollama truncates
GPU_HOG_MIB = 2048
THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


class ContextOverflowError(RuntimeError):
    """The conversation no longer fits in `NUM_CTX`; the rules would be cut."""


@dataclass(frozen=True)
class LocalReply:
    """One model reply, already stripped of thinking."""

    text: str
    seconds: float
    prompt_tokens: int


def strip_think(text: str) -> str:
    """Drop `<think>...</think>` blocks, a dangling close and a dangling open."""
    text = THINK_RE.sub("", text)
    if "</think>" in text:  # a thinking build opens the block in its template
        text = text.rsplit("</think>", 1)[1]
    if "<think>" in text:
        text = text.split("<think>", 1)[0]
    return text.strip()


def http_json(
    url: str, payload: dict[str, Any] | None, timeout: float
) -> dict[str, Any]:
    """POST `payload` as JSON (GET when None) and decode the JSON answer."""
    if not url.startswith(OLLAMA_URL + "/"):
        msg = f"refusing a non-Ollama URL: {url}"
        raise ValueError(msg)
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # localhost only
        answer: dict[str, Any] = json.loads(resp.read().decode())
    return answer


def estimate_tokens(messages: list[dict[str, str]]) -> int:
    """Upper-ish bound on prompt tokens, from character count."""
    return int(sum(len(m["content"]) for m in messages) / CHARS_PER_TOKEN)


def chat(
    messages: list[dict[str, str]],
    *,
    post: Callable[[str, dict[str, Any] | None, float], dict[str, Any]] = http_json,
    clock: Callable[[], float] = time.monotonic,
) -> LocalReply:
    """Ask the local model for the next assistant message.

    Raises:
        ContextOverflowError: when the prompt would not fit in `NUM_CTX`.
    """
    if estimate_tokens(messages) >= NUM_CTX:
        msg = f"conversation too long for num_ctx={NUM_CTX}; start a new session"
        raise ContextOverflowError(msg)
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "think": False,
        "keep_alive": KEEP_ALIVE,
        "options": {"num_ctx": NUM_CTX, "temperature": TEMPERATURE},
    }
    start = clock()
    data = post(f"{OLLAMA_URL}/api/chat", payload, REQUEST_TIMEOUT_S)
    seconds = clock() - start
    prompt_tokens = int(data.get("prompt_eval_count") or 0)
    if prompt_tokens >= NUM_CTX:
        msg = f"Ollama evaluated {prompt_tokens} prompt tokens >= num_ctx={NUM_CTX}"
        raise ContextOverflowError(msg)
    text = strip_think(str(data.get("message", {}).get("content") or ""))
    return LocalReply(text=text, seconds=seconds, prompt_tokens=prompt_tokens)


def model_loaded(
    post: Callable[[str, dict[str, Any] | None, float], dict[str, Any]] = http_json,
) -> bool:
    """Whether `MODEL` is already resident (then loading costs nothing new)."""
    data = post(f"{OLLAMA_URL}/api/ps", None, 5.0)
    return any(m.get("name") == MODEL for m in data.get("models", []))


def gpu_hogs(
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> list[tuple[str, int]]:
    """Non-Ollama GPU processes holding more than `GPU_HOG_MIB` (likely a game).

    Loading an 18 GB model next to one would either starve it or spill the
    model onto the CPU, so the REPL asks first.
    """
    proc = run(
        [
            "nvidia-smi",
            "--query-compute-apps=process_name,used_memory",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    hogs = []
    for line in proc.stdout.splitlines():
        name, _, mib = line.rpartition(",")
        if not mib.strip().isdigit() or "ollama" in name.lower():
            continue
        if int(mib) > GPU_HOG_MIB:
            hogs.append((name.strip(), int(mib)))
    return hogs
