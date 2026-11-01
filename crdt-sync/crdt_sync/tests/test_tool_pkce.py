# Copyright (c) 2026 Krzysztof Rudnicki
"""Tests for ``tool/_pkce``: the verifier/challenge pair, consent URL, browser."""

from __future__ import annotations

from unittest.mock import MagicMock
import urllib.parse

from tool import _pkce

# The worked example from RFC 7636 appendix B.
_RFC_VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
_RFC_CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_challenge_matches_the_rfc_vector() -> None:
    assert _pkce.challenge_for(_RFC_VERIFIER) == _RFC_CHALLENGE


def test_make_pkce_is_random_and_self_consistent() -> None:
    first, second = _pkce.make_pkce(), _pkce.make_pkce()
    assert first.verifier != second.verifier
    assert 43 <= len(first.verifier) <= 128
    assert first.challenge == _pkce.challenge_for(first.verifier)


def test_consent_url_carries_every_pkce_field() -> None:
    url = _pkce.build_consent_url(
        client_id="cid",
        redirect_uri="http://127.0.0.1:5555",
        challenge="chal",
        state="st",
        login_hint="me@example.com",
    )
    parsed = urllib.parse.urlparse(url)
    query = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
    assert parsed.netloc == "accounts.google.com"
    assert query == {
        "client_id": "cid",
        "redirect_uri": "http://127.0.0.1:5555",
        "response_type": "code",
        "scope": "openid email profile",
        "state": "st",
        "code_challenge": "chal",
        "code_challenge_method": "S256",
        "login_hint": "me@example.com",
        "prompt": "select_account",
    }


def test_open_detached_spawns_a_new_session() -> None:
    popen = MagicMock()
    which = MagicMock(side_effect=lambda name: f"/usr/bin/{name}")
    assert _pkce.open_detached("https://x", popen=popen, which=which) is True
    args, kwargs = popen.call_args
    assert args[0] == ["/usr/bin/setsid", "/usr/bin/xdg-open", "https://x"]
    assert kwargs["start_new_session"] is True


def test_open_detached_reports_missing_tools() -> None:
    popen = MagicMock()
    which = MagicMock(return_value=None)
    assert _pkce.open_detached("https://x", popen=popen, which=which) is False
    popen.assert_not_called()
