"""Tests for Firebase writes, string maps and deletion.

Split from ``test_firebase.py`` (250-line cap), which keeps key escaping
and the read paths.
"""

from __future__ import annotations

import datetime as dt
import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from crdt_sync import (
    DatabaseNotFoundError,
    FirebaseCredentials,
    FirebaseSyncClient,
    FirebaseSyncError,
    FirebaseTokenProvider,
    MemoryCredentialStore,
    RemoteNotFoundError,
    RemoteStore,
    RemoteSyncError,
)
from crdt_sync import _firebase as fb

_DATABASE_URL = "https://example-default-rtdb.europe-west1.firebasedatabase.app"

# Named without the word "token": ruff's hardcoded-credential checks (S105 /
# S106) key off the identifier, and these are obviously fake test fixtures.
_FAKE_ID = "id-fixture"
_FAKE_REFRESH = "refresh-fixture"


def _response(status_code: int = 200, json_data: object = None) -> MagicMock:
    """Build a fake ``requests.Response`` with a status and JSON body."""
    response = MagicMock()
    response.status_code = status_code
    response.ok = 200 <= status_code < 300
    response.json = MagicMock(return_value=json_data)
    response.text = json.dumps(json_data)
    return response


def _auth(*, signed_in: bool = True) -> FirebaseTokenProvider:
    """A provider holding a long-lived token, so no auth HTTP is needed."""
    credentials = (
        FirebaseCredentials(
            id_token=_FAKE_ID,
            refresh_token=_FAKE_REFRESH,
            expires_at=dt.datetime(2099, 1, 1, tzinfo=dt.UTC),
        )
        if signed_in
        else None
    )
    return FirebaseTokenProvider("fake-api-key", MemoryCredentialStore(credentials))


def _client(*, signed_in: bool = True) -> FirebaseSyncClient:
    return FirebaseSyncClient(_DATABASE_URL, _auth(signed_in=signed_in))


class TestPutFileText:
    """Put file text."""

    def test_writes_the_text_as_a_json_string_leaf(self) -> None:
        """Writes the text as a JSON string leaf."""
        with (
            patch.object(fb.requests, "get", return_value=_response(200, None)),
            patch.object(
                fb.requests, "put", return_value=_response(200, '{"a":1}')
            ) as put_mock,
        ):
            _client().put_file_text(
                "ns/devices/pc/log.json", '{"a":1}', message="ignored"
            )
        assert put_mock.call_args.kwargs["json"] == '{"a":1}'
        assert put_mock.call_args.args[0].endswith("/log~2Ejson.json")

    def test_raises_on_a_non_2xx_response(self) -> None:
        """Raises on a non 2xx response."""
        with (
            patch.object(
                fb.requests, "put", return_value=_response(400, {"error": "bad"})
            ),
            pytest.raises(FirebaseSyncError),
        ):
            _client().put_file_text("ns/devices/pc/log.json", "{}", message="m")

    def test_turns_a_network_failure_into_a_sync_error(self) -> None:
        """Turns a network failure into a sync error."""
        with (
            patch.object(
                fb.requests, "put", side_effect=requests.ConnectionError("offline")
            ),
            pytest.raises(FirebaseSyncError, match="network error"),
        ):
            _client().put_file_text("ns/devices/pc/log.json", "{}", message="m")


class TestGetStringMap:
    """Get string map."""

    def test_returns_the_map_with_keys_decoded(self) -> None:
        """Returns the map with keys decoded."""
        payload = {"pc": "sha-1", "phone": "sha-2"}
        with patch.object(fb.requests, "get", return_value=_response(200, payload)):
            assert _client().get_string_map("ns/revs") == payload

    def test_degrades_to_empty_when_absent(self) -> None:
        """Degrades to empty when absent."""
        with patch.object(fb.requests, "get", return_value=_response(200, None)):
            assert not _client().get_string_map("ns/revs")

    def test_skips_non_string_entries_rather_than_failing(self) -> None:
        # The revs node is an optimisation; a corrupt one must degrade into
        # "fetch everything", never into a failed tick.
        """Skips non string entries rather than failing."""
        with patch.object(
            fb.requests, "get", return_value=_response(200, {"pc": "sha-1", "b": 42})
        ):
            assert _client().get_string_map("ns/revs") == {"pc": "sha-1"}

    def test_raises_on_a_non_2xx_response(self) -> None:
        """Raises on a non 2xx response."""
        with (
            patch.object(
                fb.requests, "get", return_value=_response(500, {"error": "boom"})
            ),
            pytest.raises(FirebaseSyncError),
        ):
            _client().get_string_map("ns/revs")


class TestDeleteFile:
    """Delete file."""

    def test_sends_a_delete_to_the_escaped_path(self) -> None:
        """Sends a delete to the escaped path."""
        with patch.object(
            fb.requests, "delete", return_value=_response(200, None)
        ) as delete_mock:
            _client().delete_file("ns/devices/pc/log.json")
        assert delete_mock.call_args.args[0].endswith("/log~2Ejson.json")

    def test_raises_on_a_non_2xx_response(self) -> None:
        """Raises on a non 2xx response."""
        with (
            patch.object(
                fb.requests, "delete", return_value=_response(500, {"error": "boom"})
            ),
            pytest.raises(FirebaseSyncError),
        ):
            _client().delete_file("ns/devices/pc/log.json")

    def test_turns_a_network_failure_into_a_sync_error(self) -> None:
        """Turns a network failure into a sync error."""
        with (
            patch.object(
                fb.requests, "delete", side_effect=requests.ConnectionError("x")
            ),
            pytest.raises(FirebaseSyncError, match="network error"),
        ):
            _client().delete_file("ns/devices/pc/log.json")


class TestCanAccessRemote:
    """Can access remote."""

    def test_true_when_the_database_root_reads(self) -> None:
        """True when the database root reads."""
        with patch.object(fb.requests, "get", return_value=_response(200, {"ns": 1})):
            assert _client().can_access_remote() is True

    def test_false_when_the_rules_reject_the_token(self) -> None:
        """False when the rules reject the token."""
        with patch.object(
            fb.requests, "get", return_value=_response(401, {"error": "denied"})
        ):
            assert _client().can_access_remote() is False

    def test_false_on_a_network_error(self) -> None:
        """False on a network error."""
        with patch.object(
            fb.requests, "get", side_effect=requests.ConnectionError("offline")
        ):
            assert _client().can_access_remote() is False

    def test_false_when_not_signed_in_rather_than_raising(self) -> None:
        # "cannot get a token" is exactly "cannot access the remote", and a
        # settings Test-connection button must not blow up.
        """False when not signed in rather than raising."""
        assert _client(signed_in=False).can_access_remote() is False


class TestRemoteStoreContract:
    """Remote store contract."""

    def test_the_client_satisfies_remote_store(self) -> None:
        """The client satisfies remote store."""
        assert isinstance(_client(), RemoteStore)

    def test_database_not_found_is_catchable_as_either_error(self) -> None:
        """Database not found is catchable as either error."""
        error = DatabaseNotFoundError("gone")
        assert isinstance(error, FirebaseSyncError)
        assert isinstance(error, RemoteNotFoundError)
        assert isinstance(error, RemoteSyncError)

    def test_a_trailing_slash_on_the_database_url_is_tolerated(self) -> None:
        """A trailing slash on the database URL is tolerated."""
        client = FirebaseSyncClient(f"{_DATABASE_URL}/", _auth())
        with patch.object(
            fb.requests, "get", return_value=_response(200, "ok")
        ) as get_mock:
            client.get_file_text("ns/x.json")
        assert get_mock.call_args.args[0] == f"{_DATABASE_URL}/ns/x~2Ejson.json"
