"""Tests for ``seed_apps`` in ``tool/seed_session``.

``main()`` is covered in :mod:`test_tool_seed_session_main`, split to stay
under the 250-line cap.

The reason this script exists is that credential files were present and the
tokens inside them were dead, so "the file was written" proves nothing. Two
structural decisions follow from that and are what the tests pin: every app
gets its own exchange, and verification happens in a *second pass* after all
sessions exist -- because minting a new session for the same uid can
invalidate an earlier app's refresh token, which a check-as-you-go loop would
never see.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from crdt_sync import FirebaseConfig
from crdt_sync._firebase_auth import FirebaseAuthError
from crdt_sync._remote import RemoteSyncError
from tool import seed_session as ss

_UID = "the-uid-pinned-in-the-rules"
_CONFIG = FirebaseConfig(
    api_key="AIzaSyAthisIsTheWebApiKeyFormat",
    database_url="https://project-default-rtdb.firebasedatabase.app",
    project_id="the-project",
    uid=_UID,
    email="sync@example.com",
)
_ID_VALUE = "the-google-id-token"
_APPS = ("diet_guard", "screen_locker")


@pytest.fixture
def seeding() -> tuple[MagicMock, MagicMock, MagicMock]:
    """Patch the auth provider, credential store and sync client."""
    provider = MagicMock()
    provider.sign_in_with_google.return_value = "person@gmail.com"

    with (
        patch.object(ss, "FirebaseTokenProvider", return_value=provider) as factory,
        patch.object(ss, "credential_store_for") as store_for,
        patch.object(ss, "FirebaseSyncClient") as client_factory,
    ):
        yield factory, store_for, client_factory


def test_every_named_app_is_seeded_and_returned(seeding: tuple) -> None:
    """The happy path returns the apps that verified, in order."""
    assert ss.seed_apps(_CONFIG, _ID_VALUE, _APPS) == list(_APPS)


def test_each_app_gets_its_own_credential_store(seeding: tuple) -> None:
    """A single session copied across apps would have them all refreshing
    the same rotated token and invalidating each other."""
    _, store_for, _ = seeding

    ss.seed_apps(_CONFIG, _ID_VALUE, _APPS)

    seeded_names = [call.args[0] for call in store_for.call_args_list]
    assert set(seeded_names) == set(_APPS)


def test_each_app_gets_its_own_exchange(seeding: tuple) -> None:
    """One sign-in per app, not one shared session."""
    factory, _, _ = seeding
    provider = factory.return_value

    ss.seed_apps(_CONFIG, _ID_VALUE, _APPS)

    assert provider.sign_in_with_google.call_count == len(_APPS)


def test_the_expected_uid_is_pinned_on_every_exchange(seeding: tuple) -> None:
    """A wrong account must be refused before anything is written."""
    factory, _, _ = seeding
    provider = factory.return_value

    ss.seed_apps(_CONFIG, _ID_VALUE, _APPS)

    for call in provider.sign_in_with_google.call_args_list:
        assert call.args[0] == _ID_VALUE
        assert call.kwargs["expected_uid"] == _UID


def test_a_rejected_token_stops_before_any_app_is_verified(seeding: tuple) -> None:
    """Raised on the first failure, so a wrong account reaches no app."""
    factory, _, client_factory = seeding
    factory.return_value.sign_in_with_google.side_effect = FirebaseAuthError("nope")

    with pytest.raises(FirebaseAuthError):
        ss.seed_apps(_CONFIG, _ID_VALUE, _APPS)

    client_factory.assert_not_called()


def test_verification_happens_after_every_session_exists(seeding: tuple) -> None:
    """The structural point of the two-pass design.

    Checking each app as it is written would pass an app that a later
    exchange then invalidates -- precisely the failure being guarded against.
    """
    factory, _, client_factory = seeding
    order: list[str] = []

    def _record_seed(*_args: object, **_kwargs: object) -> str:
        order.append("seed")
        return "person@gmail.com"

    def _record_verify(_path: str) -> None:
        order.append("verify")

    factory.return_value.sign_in_with_google.side_effect = _record_seed
    client_factory.return_value.list_directory.side_effect = _record_verify

    ss.seed_apps(_CONFIG, _ID_VALUE, _APPS)

    assert order == ["seed", "seed", "verify", "verify"]


def test_each_app_is_verified_with_a_real_authenticated_read(
    seeding: tuple,
) -> None:
    """A written credential file is not evidence of working sync."""
    _, _, client_factory = seeding

    ss.seed_apps(_CONFIG, _ID_VALUE, _APPS)

    client = client_factory.return_value
    assert client.list_directory.call_count == len(_APPS)
    for call in client.list_directory.call_args_list:
        # The database root, which is where the rules grant .read.
        assert call.args == ("",)


def test_the_client_is_built_against_the_configured_database(
    seeding: tuple,
) -> None:
    """Verifying against the wrong database would prove nothing."""
    _, _, client_factory = seeding

    ss.seed_apps(_CONFIG, _ID_VALUE, _APPS)

    assert client_factory.call_args.args[0] == _CONFIG.database_url


@pytest.mark.parametrize(
    "failure",
    [RemoteSyncError("rules denied"), FirebaseAuthError("token dead")],
)
def test_a_session_that_cannot_read_is_a_seed_error(
    seeding: tuple,
    failure: Exception,
) -> None:
    """Both failure shapes are caught, and neither reads as success.

    list_directory is used rather than can_access_remote() precisely so these
    stay distinguishable in the message.
    """
    _, _, client_factory = seeding
    client_factory.return_value.list_directory.side_effect = failure

    with pytest.raises(ss.SeedError, match="cannot read the database"):
        ss.seed_apps(_CONFIG, _ID_VALUE, _APPS)


def test_a_seed_error_names_the_failing_app(seeding: tuple) -> None:
    """Which app broke is the first thing needed to fix it."""
    _, _, client_factory = seeding
    client_factory.return_value.list_directory.side_effect = RemoteSyncError("denied")

    with pytest.raises(ss.SeedError, match="diet_guard was seeded but cannot read"):
        ss.seed_apps(_CONFIG, _ID_VALUE, _APPS)


def test_a_seed_error_carries_the_apps_already_verified(seeding: tuple) -> None:
    """So a partial run reports what is left instead of being reconstructed."""
    _, _, client_factory = seeding
    client_factory.return_value.list_directory.side_effect = [
        None,
        RemoteSyncError("denied"),
    ]

    with pytest.raises(ss.SeedError) as raised:
        ss.seed_apps(_CONFIG, _ID_VALUE, _APPS)

    assert raised.value.done == ("diet_guard",)


def test_a_seed_error_defaults_to_no_completed_apps() -> None:
    """Constructed without a done tuple, nothing is claimed as working."""
    assert ss.SeedError("something broke").done == ()


def test_seeding_no_apps_is_a_no_op(seeding: tuple) -> None:
    """An empty selection must not report a spurious success."""
    _, _, client_factory = seeding

    assert ss.seed_apps(_CONFIG, _ID_VALUE, ()) == []
    client_factory.assert_not_called()


def test_the_account_email_is_reported_per_app(
    seeding: tuple,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The operator's check that the right Google account was used."""
    with caplog.at_level(logging.INFO, logger="seed_session"):
        ss.seed_apps(_CONFIG, _ID_VALUE, ("diet_guard",))

    assert "diet_guard seeded as person@gmail.com" in caplog.text


def test_the_config_email_is_used_when_google_returns_none(
    seeding: tuple,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Not every exchange echoes an email; the line must still be useful."""
    factory, _, _ = seeding
    factory.return_value.sign_in_with_google.return_value = None

    with caplog.at_level(logging.INFO, logger="seed_session"):
        ss.seed_apps(_CONFIG, _ID_VALUE, ("diet_guard",))

    assert f"diet_guard seeded as {_CONFIG.email}" in caplog.text
