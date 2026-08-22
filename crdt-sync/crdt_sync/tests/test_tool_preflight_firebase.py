"""Tests for the individual checks in ``tool/preflight_firebase``.

``main()`` and the loading helpers are covered in
:mod:`test_tool_preflight_firebase_main`, split to stay under the 250-line cap.

The point of this tool is that each check names one specific misconfiguration,
because the failures it catches are otherwise indistinguishable once data has
started moving. So every check is asserted on its *message*, not just on the
fact that it raised -- a check that fires with the wrong explanation sends the
reader to the wrong place, which is the cost this module exists to avoid.
"""

from __future__ import annotations

import base64
import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from tool import preflight_firebase as pf

_UID = "the-uid-pinned-in-the-rules"
_GOOD = {
    "apiKey": "AIzaSyAthisIsTheWebApiKeyFormat",
    "databaseUrl": "https://project-default-rtdb.europe-west1.firebasedatabase.app",
    "projectId": "the-project",
    "uid": _UID,
    "email": "sync@example.com",
}
_PASSWORD = "the-sync-account-password"


def _config(**overrides: str) -> dict[str, str]:
    """A valid config with individual fields overridden."""
    return {**_GOOD, **overrides}


def test_keys_present_accepts_a_complete_config() -> None:
    """The happy path raises nothing."""
    pf.check_keys_present(_config())


@pytest.mark.parametrize("key", ["apiKey", "databaseUrl", "projectId", "uid", "email"])
def test_every_required_key_is_actually_required(key: str) -> None:
    """Each of the five keys is checked, not just the first."""
    config = _config()
    del config[key]

    with pytest.raises(pf.PreflightError, match=key):
        pf.check_keys_present(config)


def test_a_whitespace_only_value_counts_as_missing() -> None:
    """A key present but blank is the same failure as an absent one."""
    with pytest.raises(pf.PreflightError, match="uid"):
        pf.check_keys_present(_config(uid="   "))


def test_all_missing_keys_are_reported_together() -> None:
    """Reporting one at a time would need five runs to fix five typos."""
    config = {"apiKey": _GOOD["apiKey"]}

    with pytest.raises(pf.PreflightError) as raised:
        pf.check_keys_present(config)

    assert "databaseUrl" in str(raised.value)
    assert "email" in str(raised.value)


def test_no_placeholders_accepts_a_filled_in_config() -> None:
    """Real values pass."""
    pf.check_no_placeholders(_config(), _PASSWORD)


def test_an_unreplaced_scaffold_placeholder_is_caught() -> None:
    """The scaffold ships PASTE_ markers; one left behind is a typo."""
    with pytest.raises(pf.PreflightError, match="projectId"):
        pf.check_no_placeholders(_config(projectId="PASTE_PROJECT_ID"), _PASSWORD)


def test_a_placeholder_in_the_password_file_is_caught() -> None:
    """The password lives in its own file and is easy to forget."""
    with pytest.raises(pf.PreflightError, match="password"):
        pf.check_no_placeholders(_config(), "PASTE_PASSWORD_HERE")


def test_shapes_accepts_well_formed_values() -> None:
    """The happy path raises nothing."""
    pf.check_shapes(_config(), _PASSWORD)


def test_a_non_https_database_url_is_rejected() -> None:
    """http:// would work locally and fail everywhere else."""
    with pytest.raises(pf.PreflightError, match="must start with https://"):
        pf.check_shapes(
            _config(databaseUrl="http://project.firebasedatabase.app"), _PASSWORD
        )


def test_a_trailing_slash_on_the_database_url_is_rejected() -> None:
    """It yields a double slash in every request path built from it."""
    with pytest.raises(pf.PreflightError, match="must not end with"):
        pf.check_shapes(_config(databaseUrl=f"{_GOOD['databaseUrl']}/"), _PASSWORD)


def test_an_api_key_in_the_wrong_format_is_rejected() -> None:
    """Pasting a service-account key instead of the Web API key."""
    with pytest.raises(pf.PreflightError, match="AIza"):
        pf.check_shapes(_config(apiKey="ya29.not-the-web-api-key"), _PASSWORD)


def test_a_password_with_a_trailing_newline_is_rejected() -> None:
    """The single most likely hand-editing mistake, per the module docstring."""
    with pytest.raises(pf.PreflightError, match="whitespace"):
        pf.check_shapes(_config(), f"{_PASSWORD}\n")


def test_an_email_without_an_at_sign_is_rejected() -> None:
    """A uid pasted into the email field, typically."""
    with pytest.raises(pf.PreflightError, match="does not look like an address"):
        pf.check_shapes(_config(email="not-an-address"), _PASSWORD)


def _get(status: int, payload: object = None) -> MagicMock:
    """Fake a ``requests.get`` response with a status and JSON body."""
    response = MagicMock()
    response.status_code = status
    if isinstance(payload, ValueError):
        response.json.side_effect = payload
    else:
        response.json.return_value = payload if payload is not None else {}
    return response


def test_a_denied_anonymous_read_is_the_expected_outcome() -> None:
    """401 means the rules are published and doing their job."""
    with patch.object(pf.requests, "get", return_value=_get(401)):
        pf.check_rules_deny_anonymous(_config())


def test_a_world_readable_database_is_reported_loudly() -> None:
    """A 200 here means anyone on the internet can read the data."""
    with (
        patch.object(pf.requests, "get", return_value=_get(200)),
        pytest.raises(pf.PreflightError, match="world-readable"),
    ):
        pf.check_rules_deny_anonymous(_config())


def test_a_wrong_region_url_reports_the_correct_one() -> None:
    """Firebase answers 404 with the real URL rather than an error.

    Without this branch the wrong-region case would pass preflight, pass
    sign-in (a different host entirely) and only break mid-migration.
    """
    body = {
        "correctUrl": "https://project-default-rtdb.asia-southeast1.firebasedatabase.app"
    }

    with (
        patch.object(pf.requests, "get", return_value=_get(404, body)),
        pytest.raises(pf.PreflightError, match="asia-southeast1"),
    ):
        pf.check_rules_deny_anonymous(_config())


def test_a_404_without_a_correct_url_reports_a_missing_database() -> None:
    """No database at that URL at all."""
    with (
        patch.object(pf.requests, "get", return_value=_get(404)),
        pytest.raises(pf.PreflightError, match="no database lives there"),
    ):
        pf.check_rules_deny_anonymous(_config())


def test_a_404_with_an_unparseable_body_still_reports_a_missing_database() -> None:
    """The body is not guaranteed to be JSON; that must not mask the 404."""
    response = _get(404, ValueError("not json"))

    with (
        patch.object(pf.requests, "get", return_value=response),
        pytest.raises(pf.PreflightError, match="no database lives there"),
    ):
        pf.check_rules_deny_anonymous(_config())


def _token_for(uid: str) -> str:
    """Build a JWT whose payload carries ``uid`` as ``user_id``."""
    payload = base64.urlsafe_b64encode(json.dumps({"user_id": uid}).encode())
    return f"header.{payload.decode().rstrip('=')}.signature"


def _provider(uid: str) -> MagicMock:
    """A FirebaseTokenProvider that signs in and yields ``uid``'s token."""
    provider = MagicMock()
    provider.id_token.return_value = _token_for(uid)
    return provider


def test_sign_in_with_the_pinned_uid_passes() -> None:
    """The decisive check, in its passing form."""
    with patch.object(pf, "FirebaseTokenProvider", return_value=_provider(_UID)):
        pf.check_sign_in_uid_matches(_config(), _PASSWORD)


def test_signing_in_as_a_different_uid_is_rejected() -> None:
    """Authenticates fine, then denies every read and write."""
    with (
        patch.object(
            pf, "FirebaseTokenProvider", return_value=_provider("another-uid")
        ),
        pytest.raises(pf.PreflightError, match="every read and write would be denied"),
    ):
        pf.check_sign_in_uid_matches(_config(), _PASSWORD)


def test_the_uid_is_read_from_sub_when_user_id_is_absent() -> None:
    """Not every issuer sets user_id; sub is the standard claim."""
    payload = base64.urlsafe_b64encode(json.dumps({"sub": _UID}).encode())
    provider = MagicMock()
    provider.id_token.return_value = f"h.{payload.decode().rstrip('=')}.s"

    with patch.object(pf, "FirebaseTokenProvider", return_value=provider):
        pf.check_sign_in_uid_matches(_config(), _PASSWORD)


def test_the_password_is_passed_to_sign_in_verbatim() -> None:
    """A stripped or re-encoded password would fail for the wrong reason."""
    provider = _provider(_UID)

    with patch.object(pf, "FirebaseTokenProvider", return_value=provider):
        pf.check_sign_in_uid_matches(_config(), _PASSWORD)

    provider.sign_in.assert_called_once_with(_GOOD["email"], _PASSWORD)


def test_requests_exceptions_are_not_swallowed_by_the_checks() -> None:
    """Transport errors belong to main(), which reports them differently."""
    with (
        patch.object(pf.requests, "get", side_effect=requests.ConnectionError("down")),
        pytest.raises(requests.ConnectionError),
    ):
        pf.check_rules_deny_anonymous(_config())
