# Copyright (c) 2026 Krzysztof Rudnicki
"""Tests for ``tool/verify_desktop_client``: the PKCE loopback + Firebase check.

No browser, no network, no socket: the consent step, the code exchange and
Firebase's REST endpoint are all faked at the module boundary.
"""

from __future__ import annotations

import base64
import contextlib
import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from crdt_sync._autherrors import FirebaseAuthError
from crdt_sync._config import FirebaseConfig
from tool import verify_desktop_client as vdc
from tool._token_exchange import TokenError, _exchange_code
from tool.desktop_client import DesktopClient

if TYPE_CHECKING:
    from collections.abc import Iterator

_HELD = "stored-client-credential"
_CLIENT = DesktopClient("1-abc.apps.googleusercontent.com", _HELD, "kuhy-syncs")
_CONFIG = FirebaseConfig("api", "https://db", "kuhy-syncs", "uid-1", "me@example.com")
_ID_VALUE = (
    "header."
    + base64.urlsafe_b64encode(json.dumps({"aud": _CLIENT.client_id}).encode())
    .decode()
    .rstrip("=")
    + ".sig"
)


def test_audience_of_reads_the_aud_claim() -> None:
    assert vdc.audience_of(_ID_VALUE) == _CLIENT.client_id


@pytest.mark.parametrize(
    "bad", ["", "a.b", "a.!!!.c", "a." + base64.b64encode(b"[]").decode() + ".c"]
)
def test_audience_of_survives_garbage(bad: str) -> None:
    assert vdc.audience_of(bad) == "?"


@pytest.mark.parametrize(
    ("message", "needle"),
    [
        (
            "failed: HTTP 400 (INVALID_IDP_RESPONSE : id_token audience mismatch)",
            "Safelist",
        ),
        ("signed in as the wrong account: Google resolved to uid 'x'", "login_hint"),
        ("anything else", ""),
    ],
)
def test_hint_for(message: str, needle: str) -> None:
    hint = vdc.hint_for(message)
    assert (needle in hint) if needle else hint == ""


@contextlib.contextmanager
def _flow(result: dict[str, str]) -> Iterator[MagicMock]:
    """Fake the socket, the callback and the exchange; yield the exchange."""
    with (
        patch.object(vdc, "_free_port", return_value=5555),
        patch.object(
            vdc, "_start_callback_server", return_value=(MagicMock(), MagicMock())
        ),
        patch.object(vdc._CallbackHandler, "result", result),
        patch.object(vdc, "_exchange_code", return_value=_ID_VALUE) as exchange,
        patch.object(
            vdc.secrets,
            "token_urlsafe",
            side_effect=lambda nbytes: "st" if nbytes == 16 else "v" * 86,
        ),
    ):
        yield exchange


def test_fetch_id_token_sends_pkce_and_the_secret() -> None:
    opener = MagicMock(return_value=True)
    with _flow({"code": "abc", "state": "st"}) as exchange:
        token = vdc.fetch_id_token(_CLIENT, "me@example.com", opener=opener)
    assert token == _ID_VALUE
    url = opener.call_args.args[0]
    assert "redirect_uri=http%3A%2F%2F127.0.0.1%3A5555" in url
    assert "code_challenge_method=S256" in url
    code, client_id, held, redirect, verifier = exchange.call_args.args
    assert (code, client_id, held) == ("abc", _CLIENT.client_id, _HELD)
    assert redirect == "http://127.0.0.1:5555"
    assert len(verifier) >= 43


def test_fetch_id_token_without_a_browser_still_waits() -> None:
    opener = MagicMock(return_value=False)
    with _flow({"code": "abc", "state": "st"}):
        token = vdc.fetch_id_token(_CLIENT, "", open_browser=False, opener=opener)
    assert token == _ID_VALUE
    opener.assert_not_called()


def test_fetch_id_token_reports_a_refused_consent() -> None:
    with (
        _flow({"error": "access_denied"}),
        pytest.raises(TokenError, match="access_denied"),
    ):
        vdc.fetch_id_token(_CLIENT, "", opener=MagicMock())


def _firebase_reply(*, ok: bool, body: dict[str, object]) -> MagicMock:
    response = MagicMock(ok=ok, status_code=200 if ok else 400)
    response.json.return_value = body
    return response


def test_sign_in_returns_the_email_and_writes_no_file() -> None:
    reply = _firebase_reply(
        ok=True,
        body={
            "localId": "uid-1",
            "email": "me@example.com",
            "idToken": "i",
            "refreshToken": "r",
            "expiresIn": "3600",
        },
    )
    with patch("crdt_sync._firebase_auth.requests.post", return_value=reply) as post:
        assert vdc.sign_in(_CONFIG, _ID_VALUE) == "me@example.com"
    assert "signInWithIdp" in post.call_args.args[0]


def test_sign_in_surfaces_the_exact_firebase_error() -> None:
    reply = _firebase_reply(
        ok=False,
        body={
            "error": {"message": "INVALID_IDP_RESPONSE : id_token audience mismatch"}
        },
    )
    with (
        patch("crdt_sync._firebase_auth.requests.post", return_value=reply),
        pytest.raises(FirebaseAuthError, match="audience mismatch"),
    ):
        vdc.sign_in(_CONFIG, _ID_VALUE)


def test_exchange_sends_the_pkce_verifier() -> None:
    reply = MagicMock(ok=True)
    reply.json.return_value = {"id_token": _ID_VALUE}
    with patch("tool._token_exchange.requests.post", return_value=reply) as post:
        _exchange_code("c", "id", _HELD, "http://127.0.0.1:1", "ver")
    assert post.call_args.kwargs["data"]["code_verifier"] == "ver"
