"""Tests for the Ollama transport of the offline /leetcode coach."""

from __future__ import annotations

import io
import json
from typing import Any, Self
import urllib.request

import pytest

from leetcode_coach import local_backend
from leetcode_coach.tests._shared import completed, ollama_reply


def test_strip_think_removes_closed_and_dangling_blocks() -> None:
    assert local_backend.strip_think("<think>x</think>\nHi") == "Hi"
    assert local_backend.strip_think("Hi <think>never closed") == "Hi"
    assert local_backend.strip_think("reasoning...\n</think>\n\nAnswer") == "Answer"


def test_chat_sends_explicit_ctx_no_think_and_keep_alive() -> None:
    sent: list[dict[str, Any]] = []

    def post(url: str, payload: dict[str, Any] | None, _t: float) -> dict[str, Any]:
        assert url.endswith("/api/chat")
        assert payload is not None
        sent.append(payload)
        return ollama_reply("<think>plan</think>Answer")

    reply = local_backend.chat([{"role": "user", "content": "q"}], post=post)
    assert reply.text == "Answer"
    assert reply.prompt_tokens == 100
    assert sent[0]["think"] is False
    assert sent[0]["options"]["num_ctx"] == local_backend.NUM_CTX
    assert sent[0]["keep_alive"] == local_backend.KEEP_ALIVE
    assert sent[0]["stream"] is False


def test_chat_tolerates_an_empty_answer() -> None:
    reply = local_backend.chat(
        [{"role": "user", "content": "q"}], post=lambda *_a: {}, clock=lambda: 1.0
    )
    assert (reply.text, reply.seconds, reply.prompt_tokens) == ("", 0.0, 0)


def test_chat_refuses_a_prompt_ollama_would_truncate() -> None:
    def post(*_a: object) -> dict[str, Any]:
        return ollama_reply("x", tokens=local_backend.NUM_CTX)

    with pytest.raises(local_backend.ContextOverflowError):
        local_backend.chat([{"role": "user", "content": "q"}], post=post)
    huge = [{"role": "user", "content": "x" * local_backend.NUM_CTX * 4}]
    with pytest.raises(local_backend.ContextOverflowError):
        local_backend.chat(huge, post=post)


def test_gpu_hogs_ignores_ollama_and_small_processes() -> None:
    out = "/usr/bin/ollama, 18000\n/game/bin/witcher3.exe, 6000\nXorg, 300\nbad\n"
    hogs = local_backend.gpu_hogs(run=lambda *_a, **_k: completed(0, out))
    assert hogs == [("/game/bin/witcher3.exe", 6000)]


def test_model_loaded_reads_api_ps() -> None:
    def post(url: str, payload: object, _t: float) -> dict[str, Any]:
        assert url.endswith("/api/ps")
        assert payload is None
        return {"models": [{"name": local_backend.MODEL}]}

    assert local_backend.model_loaded(post)
    assert not local_backend.model_loaded(lambda *_a: {})


class FakeResponse(io.BytesIO):
    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def test_http_json_posts_and_gets_only_to_ollama(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[Any] = []

    def urlopen(req: Any, timeout: float) -> FakeResponse:
        seen.append((req.get_method(), req.data, timeout))
        return FakeResponse(json.dumps({"ok": True}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    url = f"{local_backend.OLLAMA_URL}/api/chat"
    assert local_backend.http_json(url, {"a": 1}, 2.0) == {"ok": True}
    assert local_backend.http_json(url, None, 3.0) == {"ok": True}
    assert seen == [("POST", b'{"a": 1}', 2.0), ("GET", None, 3.0)]
    with pytest.raises(ValueError, match="non-Ollama URL"):
        local_backend.http_json("http://example.com/api/chat", None, 1.0)
