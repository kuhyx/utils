"""Tests for the OmniRoute transport and the free chain (OmniRoute, then Ollama)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
import urllib.error

import pytest

from leetcode_coach import free_chain, local_backend, omniroute_backend
from leetcode_coach.tests._fake_omniroute import FakeOmniRoute

if TYPE_CHECKING:
    from pathlib import Path

Q = [{"role": "user", "content": "q"}]


def _answer(text: str | None, model: str = "groq/llama") -> dict[str, Any]:
    return {"model": model, "choices": [{"message": {"content": text}}]}


def test_chat_asks_free_best_with_a_real_budget() -> None:
    sent: list[dict[str, Any]] = []

    def post(url: str, payload: dict[str, Any], _t: float) -> dict[str, Any]:
        assert url.endswith("/v1/chat/completions")
        sent.append(payload)
        return _answer("<think>x</think>Hint")

    reply = omniroute_backend.chat(Q, post=post, clock=lambda: 2.0)

    assert (reply.text, reply.via, reply.model) == ("Hint", "omniroute", "groq/llama")
    assert sent[0]["model"] == "free-best"
    assert sent[0]["max_tokens"] >= 1000
    assert sent[0]["stream"] is False


@pytest.mark.parametrize("body", [_answer(None), _answer("  "), {"choices": []}, {}])
def test_an_empty_answer_is_a_gateway_error(body: dict[str, Any]) -> None:
    """``content: null`` (a reasoning member out of budget) must fall through."""
    with pytest.raises(omniroute_backend.GatewayError):
        omniroute_backend.chat(Q, post=lambda *_a: body)


def test_a_prompt_over_the_combo_limit_overflows() -> None:
    big = [{"role": "user", "content": "x" * (omniroute_backend.CONTEXT_TOKENS * 4)}]
    with pytest.raises(local_backend.ContextOverflowError):
        omniroute_backend.chat(big, post=lambda *_a: _answer("x"))


def test_http_json_sends_the_bearer_key(tmp_path: Path) -> None:
    key = tmp_path / "api_key"
    key.write_text("sekrit\n", encoding="utf-8")
    with FakeOmniRoute(["Hint"]) as fake:
        got = omniroute_backend.http_json(
            fake.url + "/v1/chat/completions", {"x": 1}, 5.0, key_file=key
        )
    assert got["choices"][0]["message"]["content"] == "Hint"
    assert fake.auth == ["Bearer sekrit"]
    assert json.loads(fake.bodies[0]) == {"x": 1}


def test_http_json_refuses_a_remote_url(tmp_path: Path) -> None:
    """The prompts may only go to the local gateway."""
    with pytest.raises(ValueError, match="non-loopback"):
        omniroute_backend.http_json("https://example.com/v1", {}, 1.0)


def test_a_missing_key_is_a_gateway_error(tmp_path: Path) -> None:
    with pytest.raises(omniroute_backend.GatewayError, match="key"):
        omniroute_backend.read_key(tmp_path / "nope")


def test_the_chain_answers_from_omniroute_first() -> None:
    def ollama(*_a: object, **_k: object) -> local_backend.LocalReply:
        msg = "Ollama must not be asked"
        raise AssertionError(msg)

    def omni(_m: object, **_k: object) -> local_backend.LocalReply:
        return local_backend.LocalReply("Hint", 1.0, 0, via="omniroute")

    reply = free_chain.chat(Q, timeout=5.0, rungs=(omni, ollama))
    assert reply.via == "omniroute"


@pytest.mark.parametrize(
    "error",
    [
        urllib.error.URLError("refused"),
        ConnectionRefusedError(),
        omniroute_backend.GatewayError("empty"),
        local_backend.ContextOverflowError("big"),
        TimeoutError(),
    ],
)
def test_the_chain_falls_through_to_ollama(error: Exception) -> None:
    seen: list[str] = []

    def omni(_m: object, **_k: object) -> local_backend.LocalReply:
        raise error

    def ollama(_m: object, **kw: object) -> local_backend.LocalReply:
        seen.append(str(kw.get("timeout")))
        return local_backend.LocalReply("Hint", 1.0, 0)

    reply = free_chain.chat(
        Q, timeout=7.0, rungs=(omni, ollama), on_fallback=seen.append, clock=lambda: 0.0
    )
    assert reply.via == "ollama"
    assert seen[0].startswith("omniroute")
    assert seen[1] == "7.0"


def test_the_chain_raises_the_last_error_when_every_rung_fails() -> None:
    def down(_m: object, **_k: object) -> local_backend.LocalReply:
        raise ConnectionRefusedError

    with pytest.raises(ConnectionRefusedError):
        free_chain.chat(Q, rungs=(down, down))


def test_the_default_chain_uses_the_gateway_then_ollama() -> None:
    """Hermetic conftest: both are dead ports, so the chain ends in Ollama's error."""
    with pytest.raises(urllib.error.URLError, match="refused"):
        free_chain.chat(Q, timeout=2.0)


def test_the_live_gateway_url_is_loopback() -> None:
    assert omniroute_backend.DEFAULT_URL == "http://127.0.0.1:20128"
    assert omniroute_backend.MODEL == "free-best"


def test_the_chain_shares_one_deadline() -> None:
    """A slow first rung leaves the second only what is left of ``timeout``."""
    now = [0.0]
    budgets: list[float] = []

    def slow(_m: object, *, timeout: float) -> local_backend.LocalReply:
        budgets.append(timeout)
        now[0] += 8.0
        raise TimeoutError

    def last(_m: object, *, timeout: float) -> local_backend.LocalReply:
        budgets.append(timeout)
        return local_backend.LocalReply("Hint", 1.0, 0)

    free_chain.chat(Q, timeout=10.0, rungs=(slow, last), clock=lambda: now[0])
    assert budgets == [10.0, 2.0]
    now[0] = 0.0
    with pytest.raises(TimeoutError, match="no time left"):
        free_chain.chat(Q, timeout=8.5, rungs=(slow, last), clock=lambda: now[0])
