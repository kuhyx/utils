"""The one-shot local HTTP server that catches Google's OAuth redirect.

Split from :mod:`google_id_token`, which keeps the token exchange. Google
redirects the browser back to ``http://localhost:<port>`` with the code in the
query string, so something has to be listening on a free port for exactly one
request and then stop.
"""

from __future__ import annotations

import http.server
import time
import urllib.parse
import logging
import socket
import threading
from typing import TYPE_CHECKING, ClassVar
from urllib.parse import parse_qs, urlparse

if TYPE_CHECKING:
    from collections.abc import Callable

_logger = logging.getLogger(__name__)

_CONSENT_TIMEOUT_SECONDS = 300


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Captures the ``code`` (or ``error``) Google redirects back with."""

    # Set by the server owner before serving. Class attributes because
    # BaseHTTPRequestHandler is instantiated per request by the server, so
    # there is no instance to hand them to.
    expected_state: ClassVar[str] = ""
    result: ClassVar[dict[str, str]] = {}

    def do_GET(self) -> None:
        """Record the query parameters and show a closable page.

        Requests that carry neither a ``code`` nor an ``error`` are answered
        but *not* recorded: browsers fetch ``/favicon.ico`` against the
        redirect origin, and letting that count as the callback ends the flow
        before Google ever redirects, which surfaces as a consent timeout.
        """
        query = urllib.parse.urlparse(self.path).query
        params = {k: v[0] for k, v in urllib.parse.parse_qs(query).items()}
        if "code" not in params and "error" not in params:
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        type(self).result = params

        ok = "code" in params and params.get("state") == self.expected_state
        body = (
            b"<html><body><h2>Done - you can close this tab.</h2></body></html>"
            if ok
            else b"<html><body><h2>Authorization failed.</h2></body></html>"
        )
        self.send_response(200 if ok else 400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        """Silence the default stderr request logging."""


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _start_callback_server(
    port: int,
    state: str,
) -> tuple[http.server.HTTPServer, threading.Thread]:
    """Listen on ``port`` until the OAuth callback arrives.

    Serves in a loop rather than handling exactly one request: the first
    request to reach this port is often a favicon fetch or a speculative
    preconnect, and retiring the server on it leaves nothing listening when
    Google finally redirects -- which surfaces as a consent timeout.

    Args:
        port: The loopback port to bind.
        state: The value the callback must echo back.

    Returns:
        The server and the thread serving it, so the caller can join and close.
    """
    _CallbackHandler.expected_state = state
    _CallbackHandler.result = {}
    server = http.server.HTTPServer(("127.0.0.1", port), _CallbackHandler)
    # Bounded so handle_request() returns periodically instead of blocking
    # forever; without it the loop could not notice the deadline and the
    # daemon thread would sit on the socket after the caller gave up.
    server.timeout = 1.0
    deadline = time.monotonic() + _CONSENT_TIMEOUT_SECONDS

    def _serve_until_callback() -> None:
        while not _CallbackHandler.result and time.monotonic() < deadline:
            server.handle_request()

    thread = threading.Thread(target=_serve_until_callback, daemon=True)
    thread.start()
    return server, thread
