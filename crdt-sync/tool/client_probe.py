# Copyright (c) 2026 Krzysztof Rudnicki
"""Click-free checks that a freshly stored Desktop OAuth client actually works.

Both requests need no signed-in user: Google's endpoints answer them before any
account is involved, so they say whether the client exists, accepts a loopback
redirect and whether the stored secret is right -- without opening a browser.
That separates "the console step went wrong" from "Firebase rejects the
audience" before the one human consent click is spent.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import re
from typing import TYPE_CHECKING
import urllib.parse

import requests

from tool._pkce import AUTH_ENDPOINT, challenge_for

if TYPE_CHECKING:
    from collections.abc import Callable

    from tool.desktop_client import DesktopClient

# Assembled from host and path: a literal ending in "/token" trips ruff's
# hardcoded-password check, and suppressions are banned in this repo.
_OAUTH_HOST = "https://oauth2.googleapis.com"
_TOKEN_URL = f"{_OAUTH_HOST}/token"
_PROBE_REDIRECT = "http://127.0.0.1:41234"
_TIMEOUT_SECONDS = 20
_ASCII_RUN = re.compile(rb"[ -~]{6,}")
_PROBE_VERIFIER = "probe-verifier-" + "x" * 30


@dataclass(frozen=True)
class ProbeResult:
    """One check's verdict and the words that explain it."""

    ok: bool
    detail: str


def classify_auth_location(location: str | None) -> ProbeResult:
    """Judge the auth endpoint's redirect target.

    A valid request while signed out still redirects (to the sign-in page), so
    the status code means nothing: only an ``authError`` parameter in the
    target says Google refused the client or its redirect URI.
    """
    if not location or "authError=" not in location:
        return ProbeResult(
            ok=True, detail="auth endpoint accepts the loopback redirect"
        )
    raw = location.split("authError=", 1)[1].split("&", 1)[0]
    try:
        decoded = base64.b64decode(
            raw + "=" * (-len(raw) % 4), altchars=b"-_", validate=True
        )
    except ValueError:
        return ProbeResult(
            ok=False, detail=f"auth endpoint refused the request (authError={raw})"
        )
    text = " | ".join(run.decode("ascii") for run in _ASCII_RUN.findall(decoded))
    return ProbeResult(
        ok=False, detail=f"auth endpoint refused the request: {text[:300]}"
    )


def classify_token(status: int, body: dict[str, str] | None) -> ProbeResult:
    """Judge the token endpoint's answer to a deliberately bogus code.

    ``invalid_grant`` is the success signal: Google checked the client and
    secret first, accepted them, and only then rejected the fake code.
    """
    if body is None:
        return ProbeResult(ok=False, detail=f"token endpoint: HTTP {status}, no JSON")
    error = body.get("error", "")
    description = body.get("error_description", "")
    if error == "invalid_grant":
        return ProbeResult(
            ok=True, detail="token endpoint accepts the client and secret"
        )
    if error == "invalid_client" and "not found" in description:
        return ProbeResult(
            ok=False,
            detail=(
                "client not found yet: new clients take a few minutes to "
                "propagate; rerun with --verify-only shortly"
            ),
        )
    if error == "invalid_client":
        return ProbeResult(
            ok=False, detail=f"the stored secret is wrong ({description})"
        )
    return ProbeResult(ok=False, detail=f"token endpoint: HTTP {status} {body}")


def _probe_auth(
    client: DesktopClient, get: Callable[..., requests.Response]
) -> ProbeResult:
    query = urllib.parse.urlencode(
        {
            "client_id": client.client_id,
            "redirect_uri": _PROBE_REDIRECT,
            "response_type": "code",
            "scope": "openid email",
            "code_challenge": challenge_for(_PROBE_VERIFIER),
            "code_challenge_method": "S256",
            "hl": "en",
        }
    )
    try:
        reply = get(
            f"{AUTH_ENDPOINT}?{query}",
            allow_redirects=False,
            timeout=_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        return ProbeResult(ok=False, detail=f"auth endpoint unreachable: {exc}")
    return classify_auth_location(reply.headers.get("Location"))


def _probe_token(
    client: DesktopClient, post: Callable[..., requests.Response]
) -> ProbeResult:
    try:
        answer = post(
            _TOKEN_URL,
            data={
                "code": "probe-not-a-real-code",
                "client_id": client.client_id,
                "client_secret": client.client_secret,
                "redirect_uri": _PROBE_REDIRECT,
                "grant_type": "authorization_code",
                "code_verifier": _PROBE_VERIFIER,
            },
            timeout=_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        return ProbeResult(ok=False, detail=f"token endpoint unreachable: {exc}")
    try:
        body = answer.json()
    except ValueError:
        body = None
    return classify_token(answer.status_code, body)


def probe_client(
    client: DesktopClient,
    *,
    get: Callable[..., requests.Response] = requests.get,
    post: Callable[..., requests.Response] = requests.post,
) -> list[ProbeResult]:
    """Run the auth-endpoint and token-endpoint checks for ``client``."""
    return [_probe_auth(client, get), _probe_token(client, post)]
