from __future__ import annotations

import io
import json
import sys
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path
from typing import Any, Self

import pytest

from omniroute_offload import _cli as cli
from omniroute_offload import _privacy as privacy


class FakeResp(io.BytesIO):
    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def _reply(text: str, model: str = "agnes-2.5-flash") -> FakeResp:
    body = {
        "model": model,
        "choices": [{"message": {"content": text}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 2},
    }
    return FakeResp(json.dumps(body).encode())


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[dict[str, Any]]:
    bodies: list[dict[str, Any]] = []

    def fake_urlopen(req: Any, timeout: float) -> FakeResp:
        bodies.append(json.loads(req.data))
        return _reply(f"answer{len(bodies)}")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    key = tmp_path / "api_key"
    key.write_text("k\n")
    monkeypatch.setattr(cli, "KEY_FILE", key)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    return bodies


def test_prompt_only(
    sent: list[dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["say hi"]) == 0
    out, err = capsys.readouterr()
    assert out == "answer1\n"
    assert "agnes-2.5-flash" in err
    assert sent[0]["model"] == "free-best"
    assert sent[0]["messages"][-1]["content"] == "say hi"


def test_file_is_attached(sent: list[dict[str, Any]], tmp_path: Path) -> None:
    log = Path("/tmp") / f"free_llm_test_{tmp_path.name}.log"
    log.write_text("ERROR one\n")
    try:
        assert cli.main(["-f", str(log), "list errors"]) == 0
    finally:
        log.unlink()
    content = sent[0]["messages"][-1]["content"]
    assert "ERROR one" in content
    assert content.endswith("list errors")


def test_stdin_is_attached(
    sent: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO("piped text"))
    assert cli.main(["--max-tokens", "50", "-m", "nvidia/x", "sum"]) == 0
    assert "piped text" in sent[0]["messages"][-1]["content"]
    assert sent[0]["max_tokens"] == 50
    assert sent[0]["model"] == "nvidia/x"


def test_refused_file(
    sent: list[dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["-f", str(Path.home() / ".ssh/id_rsa"), "x"]) == cli.EXIT_REFUSED
    assert "refused" in capsys.readouterr().err
    assert sent == []


def test_force_skips_path_but_not_secrets(
    sent: list[dict[str, Any]],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doc = tmp_path / "notes.txt"
    doc.write_text("plain")
    monkeypatch.setattr(privacy, "SCRATCH_ROOTS", ())
    assert cli.main(["-f", str(doc), "x"]) == cli.EXIT_REFUSED
    assert cli.main(["--force", "-f", str(doc), "x"]) == 0
    doc.write_text("AKIA" + "A" * 16)
    assert cli.main(["--force", "-f", str(doc), "x"]) == cli.EXIT_REFUSED
    assert len(sent) == 1
    capsys.readouterr()


def test_missing_file(
    sent: list[dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["--force", "-f", "/nonexistent/x.log", "x"]) == cli.EXIT_REFUSED
    assert "cannot read" in capsys.readouterr().err


def test_chunked_map_reduce(
    sent: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "CHUNK_CHARS", 10)
    monkeypatch.setattr(sys, "stdin", io.StringIO("a" * 25))
    assert cli.main(["find"]) == 0
    final = sent[-1]["messages"][-1]["content"]
    parts = int(final.split("part 1/")[1].split()[0])
    assert parts > 1
    assert len(sent) == parts + 1
    assert final.endswith("find")
    assert capsys.readouterr().out == f"answer{parts + 1}\n"


def test_split_prefers_line_breaks() -> None:
    assert cli.split_chunks("aaaa\nbbbb\ncc", 6) == ["aaaa\n", "bbbb\n", "cc"]
    assert cli.split_chunks("abcdefgh", 3) == ["abc", "def", "gh"]
    assert cli.split_chunks("", 3) == []


def test_gateway_http_error(
    monkeypatch: pytest.MonkeyPatch,
    sent: list[dict[str, Any]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail(req: Any, timeout: float) -> FakeResp:
        raise urllib.error.HTTPError(
            cli.ENDPOINT, 429, "busy", Message(), io.BytesIO(b'{"error":"cooling"}')
        )

    monkeypatch.setattr(urllib.request, "urlopen", fail)
    assert cli.main(["x"]) == cli.EXIT_GATEWAY
    assert "429" in capsys.readouterr().err


def test_gateway_down(
    monkeypatch: pytest.MonkeyPatch,
    sent: list[dict[str, Any]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    def down(req: Any, timeout: float) -> FakeResp:
        msg = "refused"
        raise urllib.error.URLError(msg)

    monkeypatch.setattr(urllib.request, "urlopen", down)
    assert cli.main(["x"]) == cli.EXIT_GATEWAY
    assert "start.sh" in capsys.readouterr().err


def test_empty_answer_is_an_error(
    monkeypatch: pytest.MonkeyPatch,
    sent: list[dict[str, Any]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: _reply(""))
    assert cli.main(["x"]) == cli.EXIT_GATEWAY
    assert "empty" in capsys.readouterr().err


def test_privacy_module_used(
    monkeypatch: pytest.MonkeyPatch, sent: list[dict[str, Any]]
) -> None:
    monkeypatch.setattr(privacy, "secret_refusal", lambda _t: "secret!")
    assert cli.main(["x"]) == cli.EXIT_REFUSED


class Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_tty_stdin_is_not_read(
    sent: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "stdin", Tty("must not be sent"))
    assert cli.main(["hi"]) == 0
    assert "must not be sent" not in sent[0]["messages"][-1]["content"]
