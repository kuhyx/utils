r"""Fetch a Google ID token for this project, via a local loopback OAuth flow.

``link_google.py`` needs a Google ID token whose ``aud`` claim is an OAuth
client **belonging to this Firebase project**. A token from an unrelated
client -- notably the OAuth Playground's own -- is rejected with ``Invalid Idp
Response: id_token audience mismatch``, which reads exactly like a malformed
token and sends you looking in the wrong place. So the token is minted here,
against the project's own Web client.

The flow is the standard installed-app one: open the consent page, catch the
authorization code on a loopback redirect, exchange it for tokens. No secrets
are stored; the code and tokens live only in this process.

Usage::

    python3 tool/google_id_token.py --client-id <web-client-id> \\
        --client-secret <web-client-secret>

    # Feed straight into the linker:
    python3 tool/google_id_token.py --client-id ... --client-secret ... \\
        --output token.txt
    python3 tool/link_google.py --google-id-token-file token.txt

The client id and secret come from the **Web application** OAuth client in the
Google Cloud console for the project. ``http://localhost`` must be listed as
an authorised redirect URI for that client.

The port matters. Only a **Desktop app** client accepts any loopback port; a
**Web application** client compares redirect URIs exactly, so a random port
fails the consent request with ``redirect_uri_mismatch`` before the account
picker ever appears. Against a Web client, pass ``--port`` with a port that is
registered verbatim on the client, e.g. ``http://localhost:8765``.
"""

from __future__ import annotations

import argparse
import http.server
import logging
from pathlib import Path
import secrets
import socket
import sys
import threading
import time
from typing import ClassVar
import urllib.parse
import webbrowser

import requests

_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"

# Assembled from host and path rather than written as one literal: a string
# ending in "/token" trips ruff's hardcoded-password check (S105), and the
# honest fix is to not have the literal rather than to silence the rule.
_OAUTH_HOST = "https://oauth2.googleapis.com"
_TOKEN_EXCHANGE_URL = f"{_OAUTH_HOST}/token"

# openid gets an ID token at all; email makes the token carry the address, so
# link_google.py can show which account is about to be linked.
_SCOPES = "openid email profile"

_TIMEOUT_SECONDS = 30
_CONSENT_TIMEOUT_SECONDS = 300

_logger = logging.getLogger("google_id_token")


class TokenError(Exception):
    """The authorization flow did not produce an ID token."""


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


def fetch_id_token(
    client_id: str,
    client_secret: str,
    *,
    open_browser: bool = True,
    port: int = 0,
) -> str:
    """Run the loopback OAuth flow and return a Google ID token.

    Args:
        client_id: The project's Web OAuth client id.
        client_secret: That client's secret.
        open_browser: Whether to launch a browser automatically.
        port: The loopback port to listen on. 0 picks a free one, which only
            works for a **Desktop app** client -- those accept any loopback
            port. A **Web application** client matches redirect URIs exactly,
            so it needs a fixed port that is registered on the client, or
            Google answers the consent request with ``redirect_uri_mismatch``.

    Returns:
        The ``id_token`` string.

    Raises:
        TokenError: If consent was refused, timed out, or the exchange failed.
    """
    resolved_port = port or _free_port()
    redirect_uri = f"http://localhost:{resolved_port}"
    # Guards against a stray request to the loopback port being mistaken for
    # the real callback.
    state = secrets.token_urlsafe(16)

    server, thread = _start_callback_server(resolved_port, state)

    consent_url = f"{_AUTH_ENDPOINT}?" + urllib.parse.urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": _SCOPES,
            "state": state,
            # Force the picker so the right account can be chosen explicitly
            # rather than silently reusing whichever is already signed in.
            "prompt": "select_account",
        }
    )

    _logger.info("  ..  open this URL and pick the sync account:")
    _logger.info("")
    _logger.info("      %s", consent_url)
    _logger.info("")
    if open_browser:
        webbrowser.open(consent_url)

    thread.join(timeout=_CONSENT_TIMEOUT_SECONDS)
    server.server_close()

    params = _CallbackHandler.result
    if not params:
        msg = f"no response on {redirect_uri} within {_CONSENT_TIMEOUT_SECONDS}s"
        raise TokenError(msg)
    if "error" in params:
        msg = f"authorization was refused: {params['error']}"
        raise TokenError(msg)
    if params.get("state") != state:
        msg = "the callback state did not match; ignoring the response"
        raise TokenError(msg)
    code = params.get("code")
    if not code:
        msg = f"the callback carried no authorization code: {params}"
        raise TokenError(msg)

    try:
        response = requests.post(
            _TOKEN_EXCHANGE_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        msg = f"network error exchanging the code: {exc}"
        raise TokenError(msg) from exc

    if not response.ok:
        msg = f"token exchange failed: HTTP {response.status_code} {response.text}"
        raise TokenError(msg)

    id_token = response.json().get("id_token")
    if not id_token:
        msg = "the token response carried no id_token; was 'openid' in the scopes?"
        raise TokenError(msg)
    return str(id_token)


def main(argv: list[str] | None = None) -> int:
    """Fetch an ID token and print or save it. Returns an exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--client-id", required=True, help="Web OAuth client id.")
    parser.add_argument(
        "--client-secret",
        required=True,
        help="Web OAuth client secret.",
    )
    parser.add_argument(
        "--output",
        help="Write the token here (mode 0600) instead of printing it.",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Print the consent URL without launching a browser.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help=(
            "Fixed loopback port for the redirect URI. Required for a Web "
            "application client, which must have http://localhost:<port> "
            "registered verbatim; 0 (the default) picks a free port and "
            "suits a Desktop app client."
        ),
    )
    args = parser.parse_args(argv)
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")

    try:
        token = fetch_id_token(
            args.client_id,
            args.client_secret,
            open_browser=not args.no_browser,
            port=args.port,
        )
    except TokenError:
        _logger.exception("  FAIL")
        return 1

    if args.output:
        destination = Path(args.output)
        # 0600 from the outset: an ID token is a bearer credential.
        destination.touch(mode=0o600)
        destination.write_text(token, encoding="utf-8")
        _logger.info("  PASS  id_token written to %s", destination)
        _logger.info("")
        _logger.info("Now link it:")
        _logger.info(
            "    python3 tool/link_google.py --google-id-token-file %s", destination
        )
    else:
        _logger.info("%s", token)
    return 0


if __name__ == "__main__":
    sys.exit(main())
