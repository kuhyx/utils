# Copyright (c) 2026 Krzysztof Rudnicki
"""PKCE pair, consent URL and detached browser launch for the loopback flow."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import secrets
import shutil
import subprocess
from typing import TYPE_CHECKING
import urllib.parse

if TYPE_CHECKING:
    from collections.abc import Callable

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
SCOPES = "openid email profile"
_VERIFIER_BYTES = 64


@dataclass(frozen=True)
class Pkce:
    """A code verifier and the S256 challenge derived from it."""

    verifier: str
    challenge: str


def challenge_for(verifier: str) -> str:
    """Return the unpadded base64url SHA-256 of ``verifier`` (RFC 7636 S256)."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def make_pkce() -> Pkce:
    """Return a fresh 86-char verifier and its challenge."""
    verifier = secrets.token_urlsafe(_VERIFIER_BYTES)
    return Pkce(verifier=verifier, challenge=challenge_for(verifier))


def build_consent_url(
    *,
    client_id: str,
    redirect_uri: str,
    challenge: str,
    state: str,
    login_hint: str,
) -> str:
    """Return the consent URL, with the sync account preselected."""
    query = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPES,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "login_hint": login_hint,
            "prompt": "select_account",
        }
    )
    return f"{AUTH_ENDPOINT}?{query}"


def open_detached(
    url: str,
    *,
    popen: Callable[..., object] = subprocess.Popen,
    which: Callable[[str], str | None] = shutil.which,
) -> bool:
    """Open ``url`` via ``setsid xdg-open``; False if either tool is missing."""
    setsid, opener = which("setsid"), which("xdg-open")
    if not setsid or not opener:
        return False
    popen(
        [setsid, opener, url],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return True
