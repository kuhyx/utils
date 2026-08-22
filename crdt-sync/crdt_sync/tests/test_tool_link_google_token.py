"""Tests for ``describe_google_token`` in ``tool/link_google``.

Split from :mod:`test_tool_link_google` (which covers linking) and
:mod:`test_tool_link_google_main` (the CLI) to stay under the 250-line cap.

These are the local, pre-network checks. They exist so a misconfiguration
reports itself here rather than as an opaque Firebase rejection, so what is
asserted is the *message* -- naming what was pasted by mistake is the entire
value of the check.
"""

from __future__ import annotations

import base64

import pytest

from crdt_sync.tests.test_tool_link_google import _google_token, _jwt
from tool import link_google as lg


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
