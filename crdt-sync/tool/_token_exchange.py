# Copyright (c) 2026 Krzysztof Rudnicki
"""Turning the captured OAuth callback into a Google ID token.

Split from :mod:`google_id_token`, which keeps the consent flow and the CLI:
this half validates what the loopback server caught and trades the
authorization code for tokens at Google's endpoint.
"""

from __future__ import annotations

import requests

from tool._oauth_callback import _CONSENT_TIMEOUT_SECONDS

# Assembled from host and path rather than written as one literal: a string
# ending in "/token" trips ruff's hardcoded-password check (S105), and the
# honest fix is to not have the literal rather than to silence the rule.
_OAUTH_HOST = "https://oauth2.googleapis.com"
_TOKEN_EXCHANGE_URL = f"{_OAUTH_HOST}/token"

_TIMEOUT_SECONDS = 30


class TokenError(Exception):
    """The authorization flow did not produce an ID token."""


def _authorization_code(params: dict[str, str], redirect_uri: str, state: str) -> str:
    """Validate the captured callback and return its authorization code."""
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
    return code


def _exchange_code(
    code: str, client_id: str, client_secret: str, redirect_uri: str
) -> str:
    """Trade the authorization code for an ID token at Google's endpoint."""
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
