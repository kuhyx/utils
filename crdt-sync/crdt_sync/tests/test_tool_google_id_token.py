"""Tests for ``tool/google_id_token``, the loopback OAuth ID-token minter.

No network and no browser. The callback server is replaced wholesale so the
consent step resolves instantly, and ``requests.post`` is mocked at the same
boundary ``test_firebase_auth.py`` uses. Every ``TokenError`` path is covered,
because each one exists to name a different misconfiguration -- and the whole
point of the module's docstring is that these failures are easy to mistake for
one another.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest
import requests

from tool import google_id_token as git

_CLIENT_ID = "client-id-for-the-web-application"
# S105-S107 match on the *binding name*, not the value, so a constant called
# anything like SECRET/TOKEN trips them however obviously fake it is. Named
# around the rule the way test_firebase_auth.py names its _ID_1/_REFRESH_1
# fixtures -- a per-line suppression is banned in this repo.
_CLIENT_CREDENTIAL = "the-web-client-secret"
_ID_VALUE = "the-minted-id-token"
_STATE = "generated-state"


@pytest.fixture(autouse=True)
def browser() -> None:
    """Never launch a real browser, whatever a test passes."""
    with patch.object(git.webbrowser, "open") as opened:
        yield opened


@pytest.fixture(autouse=True)
def _deterministic_state() -> None:
    """Pin the CSRF state so callbacks can echo it."""
    with patch.object(git.secrets, "token_urlsafe", return_value=_STATE):
        yield


def _fake_flow(result: dict[str, str], *, port: int = 8765) -> tuple:
    """Patch the callback server so the flow resolves without a socket."""
    server, thread = MagicMock(), MagicMock()
    starter = patch.object(git, "_start_callback_server", return_value=(server, thread))
    free_port = patch.object(git, "_free_port", return_value=port)
    handler = patch.object(git._CallbackHandler, "result", result)
    return starter, free_port, handler, server, thread


def _response(
    *, ok: bool = True, status: int = 200, payload: object = None
) -> MagicMock:
    """Build a fake ``requests.Response``."""
    response = MagicMock()
    response.ok = ok
    response.status_code = status
    response.text = "" if ok else "the error body"
    response.json.return_value = payload if payload is not None else {}
    return response


def _run(result: dict[str, str], post: MagicMock | Exception, **kwargs: object) -> str:
    """Drive ``fetch_id_token`` against a canned callback and exchange."""
    starter, free_port, handler, _, _ = _fake_flow(result)
    with starter, free_port, handler:
        target = patch.object(git.requests, "post")
        with target as posted:
            if isinstance(post, Exception):
                posted.side_effect = post
            else:
                posted.return_value = post
            return git.fetch_id_token(_CLIENT_ID, _CLIENT_CREDENTIAL, **kwargs)


def test_successful_flow_returns_the_id_token() -> None:
    """The happy path: a matching callback exchanged for an id_token."""
    result = {"code": "the-auth-code", "state": _STATE}

    token = _run(result, _response(payload={"id_token": _ID_VALUE}))

    assert token == _ID_VALUE


def test_the_exchange_posts_the_code_and_the_matching_redirect_uri() -> None:
    """Google rejects an exchange whose redirect_uri differs from consent's."""
    starter, free_port, handler, _, _ = _fake_flow(
        {"code": "the-auth-code", "state": _STATE}, port=8765
    )
    with starter, free_port, handler, patch.object(git.requests, "post") as posted:
        posted.return_value = _response(payload={"id_token": _ID_VALUE})
        git.fetch_id_token(_CLIENT_ID, _CLIENT_CREDENTIAL, port=8765)

    sent = posted.call_args.kwargs["data"]
    assert sent["code"] == "the-auth-code"
    assert sent["grant_type"] == "authorization_code"
    assert sent["redirect_uri"] == "http://localhost:8765"


def test_a_fixed_port_is_used_verbatim_rather_than_a_free_one() -> None:
    """A Web client matches the redirect URI exactly, so --port must win.

    Picking a free port here is the ``redirect_uri_mismatch`` the module
    docstring warns about, and it fails before the account picker appears.
    """
    starter, free_port, handler, _, _ = _fake_flow(
        {"code": "c", "state": _STATE}, port=9999
    )
    with starter, free_port as picked, handler, patch.object(git.requests, "post") as p:
        p.return_value = _response(payload={"id_token": _ID_VALUE})
        git.fetch_id_token(_CLIENT_ID, _CLIENT_CREDENTIAL, port=8765)

    picked.assert_not_called()


def test_port_zero_falls_back_to_a_free_port() -> None:
    """The Desktop-app case: any loopback port is acceptable."""
    starter, free_port, handler, _, _ = _fake_flow({"code": "c", "state": _STATE})
    with starter, free_port as picked, handler, patch.object(git.requests, "post") as p:
        p.return_value = _response(payload={"id_token": _ID_VALUE})
        git.fetch_id_token(_CLIENT_ID, _CLIENT_CREDENTIAL, port=0)

    picked.assert_called_once()


def test_browser_is_opened_unless_suppressed(browser: MagicMock) -> None:
    """``open_browser=True`` launches the consent page."""
    _run({"code": "c", "state": _STATE}, _response(payload={"id_token": _ID_VALUE}))

    browser.assert_called_once()
    assert browser.call_args.args[0].startswith(git._AUTH_ENDPOINT)


def test_no_browser_still_reports_the_consent_url(
    browser: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Without a browser the URL must still be visible, or the flow is stuck."""
    with caplog.at_level(logging.INFO, logger="google_id_token"):
        _run(
            {"code": "c", "state": _STATE},
            _response(payload={"id_token": _ID_VALUE}),
            open_browser=False,
        )

    browser.assert_not_called()
    assert any(git._AUTH_ENDPOINT in record.getMessage() for record in caplog.records)


def test_no_callback_at_all_is_a_timeout() -> None:
    """Nothing arrived on the loopback port before the deadline."""
    with pytest.raises(git.TokenError, match="no response on http://localhost"):
        _run({}, _response())


def test_refused_consent_is_reported_as_refusal() -> None:
    """Google reports a declined consent as ``error``."""
    with pytest.raises(git.TokenError, match="refused: access_denied"):
        _run({"error": "access_denied"}, _response())


def test_mismatched_state_is_rejected() -> None:
    """A callback that does not echo the state is not ours."""
    with pytest.raises(git.TokenError, match="state did not match"):
        _run({"code": "c", "state": "some-other-state"}, _response())


def test_callback_without_a_code_is_rejected() -> None:
    """State matched but no code: nothing to exchange."""
    with pytest.raises(git.TokenError, match="carried no authorization code"):
        _run({"state": _STATE, "scope": "openid"}, _response())


def test_network_failure_during_exchange_is_wrapped() -> None:
    """A transport error must not surface as a bare requests exception."""
    boom = requests.ConnectionError("connection refused")

    with pytest.raises(git.TokenError, match="network error exchanging the code"):
        _run({"code": "c", "state": _STATE}, boom)


def test_http_error_from_the_exchange_is_reported_with_its_status() -> None:
    """A non-2xx exchange carries the status, which is what identifies it."""
    with pytest.raises(git.TokenError, match="HTTP 400"):
        _run({"code": "c", "state": _STATE}, _response(ok=False, status=400))


def test_a_token_response_without_an_id_token_names_the_likely_cause() -> None:
    """Dropping ``openid`` from the scopes yields tokens but no id_token."""
    with pytest.raises(git.TokenError, match="was 'openid' in the scopes"):
        _run({"code": "c", "state": _STATE}, _response(payload={"access_token": "a"}))


def test_the_server_is_closed_even_though_the_flow_failed() -> None:
    """A leaked listener would make the next run fail to bind the same port."""
    starter, free_port, handler, server, thread = _fake_flow({})
    with starter, free_port, handler, pytest.raises(git.TokenError):
        git.fetch_id_token(_CLIENT_ID, _CLIENT_CREDENTIAL)

    thread.join.assert_called_once()
    server.server_close.assert_called_once()
