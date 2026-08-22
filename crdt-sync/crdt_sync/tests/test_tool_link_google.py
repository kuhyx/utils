"""Tests for token inspection and linking in ``tool/link_google``.

``main()`` and ``_read_token`` are covered in
:mod:`test_tool_link_google_main`, split to stay under the 250-line cap.

The failure this whole script exists to prevent is silent: linking onto a
*new* account succeeds at the auth layer and then has every read and write
denied by rules that pin one uid. So the two assertions that matter most here
are that the existing account's ``idToken`` is always sent (omitting it turns
the call into "sign in or sign up") and that a mismatched uid is a hard error.
"""

from __future__ import annotations

import base64
import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from crdt_sync import FirebaseConfig
from tool import link_google as lg

_UID = "the-uid-pinned-in-the-rules"
_CONFIG = FirebaseConfig(
    api_key="AIzaSyAthisIsTheWebApiKeyFormat",
    database_url="https://project-default-rtdb.firebasedatabase.app",
    project_id="the-project",
    uid=_UID,
    email="sync@example.com",
)


def _jwt(claims: dict[str, object]) -> str:
    """Build an unsigned JWT carrying ``claims`` as its payload."""
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode()
    return f"header.{payload.rstrip('=')}.signature"


def _google_token(**overrides: object) -> str:
    """A plausible Google ID token, with individual claims overridden."""
    claims = {
        "iss": "https://accounts.google.com",
        "email": "person@gmail.com",
        "aud": "the-web-client-id.apps.googleusercontent.com",
    }
    return _jwt({**claims, **overrides})


def _response(*, ok: bool = True, status: int = 200, body: object = None) -> MagicMock:
    """Fake a ``requests`` response from accounts:signInWithIdp."""
    response = MagicMock()
    response.ok = ok
    response.status_code = status
    response.text = "" if ok else '{"error": {"message": "INVALID_IDP_RESPONSE"}}'
    response.json.return_value = body if body is not None else {"localId": _UID}
    return response


def test_a_token_that_is_not_three_parts_is_rejected() -> None:
    """An access token or an auth code pasted by mistake.

    The message names both, because that is the actual confusion -- the
    module docstring exists because the Firebase-side error does not.
    """
    with pytest.raises(lg.LinkError, match="not an access token"):
        lg.describe_google_token("not-a-jwt")


def test_a_token_with_an_unparseable_payload_is_rejected() -> None:
    """Three parts, but the middle one is not base64url JSON."""
    with pytest.raises(lg.LinkError, match="not valid base64url JSON"):
        lg.describe_google_token("header.!!!not-base64!!!.signature")


def test_a_payload_that_is_not_an_object_is_rejected() -> None:
    """Valid base64url JSON, wrong shape."""
    payload = base64.urlsafe_b64encode(b'"just a string"').decode().rstrip("=")

    with pytest.raises(lg.LinkError, match="not a JSON object"):
        lg.describe_google_token(f"header.{payload}.signature")


def test_a_token_from_another_issuer_is_rejected() -> None:
    """The check that makes a misconfiguration report itself locally."""
    with pytest.raises(lg.LinkError, match="not Google"):
        lg.describe_google_token(_google_token(iss="https://login.example.com"))


@pytest.mark.parametrize(
    "issuer", ["https://accounts.google.com", "accounts.google.com"]
)
def test_both_google_issuer_spellings_are_accepted(issuer: str) -> None:
    """Google uses both forms; rejecting either would be a false alarm."""
    assert "person@gmail.com" in lg.describe_google_token(_google_token(iss=issuer))


def test_the_description_names_the_account_and_the_audience() -> None:
    """The operator's only chance to notice they are linking the wrong one."""
    description = lg.describe_google_token(_google_token())

    assert "person@gmail.com" in description
    assert "the-web-client-id.apps.googleusercontent.com" in description


def test_missing_optional_claims_are_described_rather_than_crashing() -> None:
    """A token without email/aud is odd but still describable."""
    token = _jwt({"iss": "accounts.google.com"})

    description = lg.describe_google_token(token)

    assert "<no email claim>" in description
    assert "<no aud claim>" in description


def test_padding_is_restored_before_decoding() -> None:
    """base64url in a JWT is unpadded; decoding without padding fails."""
    # A payload whose length is not a multiple of 4 once stripped.
    claims = {"iss": "accounts.google.com", "email": "a@b.co"}

    assert "a@b.co" in lg.describe_google_token(_jwt(claims))


def _auth_provider() -> MagicMock:
    """A token provider that signs in and yields the account's ID token."""
    auth = MagicMock()
    auth.id_token.return_value = "the-existing-account-id-token"
    return auth


def test_linking_returns_the_unchanged_uid() -> None:
    """The happy path: same uid before and after."""
    with (
        patch.object(lg, "FirebaseTokenProvider", return_value=_auth_provider()),
        patch.object(lg.requests, "post", return_value=_response()) as posted,
    ):
        result = lg.link_google(_CONFIG, _google_token())

    assert result == _UID
    assert posted.call_count == 1


def test_the_existing_id_token_is_always_sent() -> None:
    """Omitting it makes the same endpoint create a brand-new account.

    That is the silent failure the whole script exists to prevent, so it is
    asserted on the request body rather than inferred from the response.
    """
    with (
        patch.object(lg, "FirebaseTokenProvider", return_value=_auth_provider()),
        patch.object(lg.requests, "post", return_value=_response()) as posted,
    ):
        lg.link_google(_CONFIG, "the-google-token")

    sent = posted.call_args.kwargs["json"]
    assert sent["idToken"] == "the-existing-account-id-token"
    assert "id_token=the-google-token" in sent["postBody"]
    assert "providerId=google.com" in sent["postBody"]
    assert sent["returnSecureToken"] is True


def test_the_account_password_is_used_to_prove_ownership() -> None:
    """Linking requires proving ownership of the account being linked to."""
    auth = _auth_provider()
    config = MagicMock(spec=FirebaseConfig)
    config.api_key = _CONFIG.api_key
    config.email = _CONFIG.email
    config.uid = _UID
    config.read_password.return_value = "the-stored-password"

    with (
        patch.object(lg, "FirebaseTokenProvider", return_value=auth),
        patch.object(lg.requests, "post", return_value=_response()),
    ):
        lg.link_google(config, _google_token())

    auth.sign_in.assert_called_once_with(_CONFIG.email, "the-stored-password")


def test_linking_onto_a_different_uid_is_a_hard_failure() -> None:
    """The decisive check.

    A different uid authenticates perfectly and is then denied every read and
    write, so the message has to say that outright and name the remedy.
    """
    body = {"localId": "a-brand-new-uid"}

    with (
        patch.object(lg, "FirebaseTokenProvider", return_value=_auth_provider()),
        patch.object(lg.requests, "post", return_value=_response(body=body)),
        pytest.raises(lg.LinkError, match="LINKED THE WRONG ACCOUNT"),
    ):
        lg.link_google(_CONFIG, _google_token())


def test_the_wrong_account_message_names_the_unlink_remedy() -> None:
    """Knowing it failed is not enough; the console step is not obvious."""
    with (
        patch.object(lg, "FirebaseTokenProvider", return_value=_auth_provider()),
        patch.object(
            lg.requests, "post", return_value=_response(body={"localId": "x"})
        ),
        pytest.raises(lg.LinkError, match="Unlink this Google identity"),
    ):
        lg.link_google(_CONFIG, _google_token())


def test_a_response_without_a_local_id_is_rejected() -> None:
    """No uid at all must not read as a successful link."""
    with (
        patch.object(lg, "FirebaseTokenProvider", return_value=_auth_provider()),
        patch.object(lg.requests, "post", return_value=_response(body={})),
        pytest.raises(lg.LinkError, match="no localId"),
    ):
        lg.link_google(_CONFIG, _google_token())


def test_a_rejected_link_reports_the_status_and_body() -> None:
    """Firebase's own message is the only clue to why it refused."""
    response = _response(ok=False, status=400)

    with (
        patch.object(lg, "FirebaseTokenProvider", return_value=_auth_provider()),
        patch.object(lg.requests, "post", return_value=response),
        pytest.raises(lg.LinkError, match="HTTP 400"),
    ):
        lg.link_google(_CONFIG, _google_token())


def test_a_network_error_is_wrapped_as_a_link_error() -> None:
    """A bare requests exception would escape main()'s handler."""
    with (
        patch.object(lg, "FirebaseTokenProvider", return_value=_auth_provider()),
        patch.object(lg.requests, "post", side_effect=requests.Timeout("timed out")),
        pytest.raises(lg.LinkError, match="network error"),
    ):
        lg.link_google(_CONFIG, _google_token())


def test_the_timeout_is_passed_through() -> None:
    """A hung link would otherwise block the run indefinitely."""
    with (
        patch.object(lg, "FirebaseTokenProvider", return_value=_auth_provider()),
        patch.object(lg.requests, "post", return_value=_response()) as posted,
    ):
        lg.link_google(_CONFIG, _google_token(), timeout_seconds=5)

    assert posted.call_args.kwargs["timeout"] == 5
