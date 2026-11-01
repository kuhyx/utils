# Copyright (c) 2026 Krzysztof Rudnicki
"""Tests for ``tool/client_probe``: the click-free "does the client work" check."""

from __future__ import annotations

import base64
from unittest.mock import MagicMock

import requests

from tool import client_probe as probe
from tool.desktop_client import DesktopClient

_HELD = "stored-client-credential"
_CLIENT = DesktopClient(
    client_id="1-abc.apps.googleusercontent.com",
    client_secret=_HELD,
    project_id="kuhy-syncs",
)


def _location(payload: bytes) -> str:
    encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    return f"https://accounts.google.com/signin/oauth/error?authError={encoded}&x=1"


def test_auth_location_without_error_is_ok() -> None:
    result = probe.classify_auth_location("https://accounts.google.com/v3/signin")
    assert result.ok


def test_auth_location_none_is_ok() -> None:
    assert probe.classify_auth_location(None).ok


def test_auth_error_is_decoded() -> None:
    location = _location(b"\n\x0finvalid_request\x12\x02 Custom URI scheme is bad")
    result = probe.classify_auth_location(location)
    assert not result.ok
    assert "invalid_request" in result.detail
    assert "Custom URI scheme" in result.detail


def test_undecodable_auth_error_is_still_a_failure() -> None:
    result = probe.classify_auth_location(
        "https://accounts.google.com/signin/oauth/error?authError=!!!"
    )
    assert not result.ok
    assert "authError=!!!" in result.detail


def test_token_invalid_grant_means_client_and_secret_are_good() -> None:
    assert probe.classify_token(400, {"error": "invalid_grant"}).ok


def test_token_client_not_found_means_still_propagating() -> None:
    result = probe.classify_token(
        401,
        {
            "error": "invalid_client",
            "error_description": "The OAuth client was not found.",
        },
    )
    assert not result.ok
    assert "--verify-only" in result.detail


def test_token_invalid_client_means_wrong_secret() -> None:
    result = probe.classify_token(
        401, {"error": "invalid_client", "error_description": "Unauthorized"}
    )
    assert not result.ok
    assert "secret" in result.detail


def test_token_other_error_is_reported_verbatim() -> None:
    result = probe.classify_token(500, {"error": "backend_error"})
    assert not result.ok
    assert "backend_error" in result.detail


def test_token_non_json_body_is_reported() -> None:
    result = probe.classify_token(502, None)
    assert not result.ok
    assert "502" in result.detail


def _fakes(location: str | None, status: int, body: object) -> tuple:
    get = MagicMock(
        return_value=MagicMock(headers={"Location": location} if location else {})
    )
    post_response = MagicMock(status_code=status)
    if body is None:
        post_response.json.side_effect = ValueError
    else:
        post_response.json.return_value = body
    return get, MagicMock(return_value=post_response)


def test_probe_client_runs_both_checks() -> None:
    get, post = _fakes(None, 400, {"error": "invalid_grant"})
    results = probe.probe_client(_CLIENT, get=get, post=post)
    assert [r.ok for r in results] == [True, True]
    assert get.call_args.kwargs["allow_redirects"] is False
    assert post.call_args.kwargs["data"]["client_secret"] == _HELD


def test_probe_client_turns_network_errors_into_failures() -> None:
    get = MagicMock(side_effect=requests.ConnectionError("down"))
    post = MagicMock(side_effect=requests.ConnectionError("down"))
    results = probe.probe_client(_CLIENT, get=get, post=post)
    assert [r.ok for r in results] == [False, False]
    assert "down" in results[0].detail


def test_probe_client_tolerates_a_non_json_token_reply() -> None:
    get, post = _fakes(None, 502, None)
    results = probe.probe_client(_CLIENT, get=get, post=post)
    assert results[1].ok is False
    assert "502" in results[1].detail
