"""A scripted Ollama on a free localhost port, for the coach E2E tests.

Speaks the two endpoints `local_backend` uses: ``GET /api/ps`` (the model is
always "loaded", so no nvidia-smi probe runs) and ``POST /api/chat``. A chat
whose system prompt is the requirement checker's is answered from the
``checker`` queue; every other chat is the coach and comes from ``coach``.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from typing import Any

from leetcode_coach import local_backend, req_check

Seen = list[tuple[str, list[dict[str, str]]]]


class _Server(ThreadingHTTPServer):
    """Holds the scripted answers and a record of every chat request."""

    queues: dict[str, list[str]]
    seen: Seen


class _Handler(BaseHTTPRequestHandler):
    def _owner(self) -> _Server:
        assert isinstance(self.server, _Server)
        return self.server

    def _send(self, body: dict[str, Any]) -> None:
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        """`/api/ps`: the model is resident."""
        self._send({"models": [{"name": local_backend.MODEL}]})

    def do_POST(self) -> None:
        """`/api/chat`: the next scripted answer for this kind of call."""
        length = int(self.headers["Content-Length"])
        messages = json.loads(self.rfile.read(length))["messages"]
        system = messages[0]["content"] if messages else ""
        kind = "checker" if system == req_check.CHECK_SYSTEM else "coach"
        owner = self._owner()
        owner.seen.append((kind, messages))
        text = owner.queues[kind].pop(0)
        self._send({"message": {"content": text}, "prompt_eval_count": 50})


class FakeOllama:
    """Start with scripted queues; `url` goes into `local_backend.OLLAMA_URL`."""

    def __init__(self, checker: list[str], coach: list[str]) -> None:
        self.server = _Server(("127.0.0.1", 0), _Handler)
        self.server.queues = {"checker": list(checker), "coach": list(coach)}
        self.server.seen = []
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    @property
    def seen(self) -> Seen:
        """Every chat request so far, tagged checker/coach."""
        return self.server.seen

    def close(self) -> None:
        """Stop serving and release the socket."""
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
