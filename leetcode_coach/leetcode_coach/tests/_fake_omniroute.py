"""A scripted OmniRoute (OpenAI chat API) on a free localhost port.

``POST /v1/chat/completions`` answers the next scripted text as ``free-best``'s
member ``fake/free``; every request's ``Authorization`` header and body are
kept for the test to assert on.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from typing import Self


class _Server(ThreadingHTTPServer):
    answers: list[str]
    auth: list[str]
    bodies: list[bytes]


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        """The next scripted answer, in the OpenAI shape."""
        owner = self.server
        assert isinstance(owner, _Server)
        length = int(self.headers["Content-Length"])
        owner.bodies.append(self.rfile.read(length))
        owner.auth.append(self.headers.get("Authorization", ""))
        text = owner.answers.pop(0)
        body = {"model": "fake/free", "choices": [{"message": {"content": text}}]}
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_args: object) -> None:
        """Quiet."""


class FakeOmniRoute:
    """Start with scripted answers; ``url`` goes into ``LEETCODE_OMNIROUTE_URL``."""

    def __init__(self, answers: list[str]) -> None:
        """Bind a free port."""
        self._server = _Server(("127.0.0.1", 0), _Handler)
        self._server.answers = list(answers)
        self._server.auth = []
        self._server.bodies = []
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"
        self.auth = self._server.auth
        self.bodies = self._server.bodies
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> Self:
        """Serve in a thread."""
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        """Stop serving."""
        self._server.shutdown()
        self._server.server_close()
