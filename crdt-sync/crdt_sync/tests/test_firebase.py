"""Tests for the Realtime Database sync client.

The HTTP layer is fully mocked, so every branch -- success, absent path,
rules rejection, quota exhaustion, malformed values and network exceptions --
is exercised without any network access.

Key escaping is tested against the same cases as the Dart side
(``test/firebase_client_test.dart``); the two implementations must agree
byte-for-byte or a device on one would not read the other's data.
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
)
from crdt_sync import _firebase as fb
from crdt_sync._firebase import decode_key, encode_key, encode_path

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


class TestKeyEscaping:
    """Key escaping."""

    def test_escapes_a_json_filename_into_a_legal_key(self) -> None:
        # `.` is illegal in an RTDB key, and the trailing `.json` in a REST
        # URL is the format suffix -- so the name cannot be stored verbatim.
        """Escapes a JSON filename into a legal key."""
        assert encode_key("log.json") == "log~2Ejson"

    def test_leaves_dot_free_device_ids_untouched(self) -> None:
        """Leaves dot free device ids untouched."""
        assert encode_key("pc") == "pc"
        uuid = "32c28cf3-c0eb-423f-8bac-9bda9f158054"
        assert encode_key(uuid) == uuid

    def test_escapes_every_forbidden_character_and_the_escape_char(self) -> None:
        """Escapes every forbidden character and the escape char."""
        assert encode_key("a.b$c#d[e]f~g") == "a~2Eb~24c~23d~5Be~5Df~7Eg"

    @pytest.mark.parametrize(
        "name",
        ["log.json", "plain", "a.b$c#d[e]f~g", "log~2Ejson", "~", ""],
    )
    def test_round_trips(self, name: str) -> None:
        # A name that already looks like an escape must survive: `~` is
        # escaped first, so `log~2Ejson` is not mistaken for `log.json`.
        """Round trips."""
        assert decode_key(encode_key(name)) == name

    def test_escapes_each_path_segment_but_keeps_separators(self) -> None:
        """Escapes each path segment but keeps separators."""
        assert encode_path("todo-sync/notes/abc.json") == "todo-sync/notes/abc~2Ejson"

    def test_drops_empty_segments(self) -> None:
        """Drops empty segments."""
        assert not encode_path("")
        assert encode_path("/a//b/") == "a/b"


class TestGetFileText:
    """Get file text."""

    def test_returns_the_stored_text_blob(self) -> None:
        """Returns the stored text blob."""
        with patch.object(fb.requests, "get", return_value=_response(200, '{"a":1}')):
            assert _client().get_file_text("ns/devices/pc/log.json") == '{"a":1}'

    def test_requests_the_escaped_path_with_the_auth_token(self) -> None:
        """Requests the escaped path with the auth token."""
        with patch.object(
            fb.requests, "get", return_value=_response(200, "{}")
        ) as get_mock:
            _client().get_file_text("ns/devices/pc/log.json")
        url = get_mock.call_args.args[0]
        assert url.endswith("/ns/devices/pc/log~2Ejson.json")
        assert get_mock.call_args.kwargs["params"]["auth"] == _FAKE_ID

    def test_returns_none_for_a_path_never_written_to(self) -> None:
        # RTDB answers a missing path with literal null and a 200, so this is
        # benign "no other device has synced yet", not an error.
        """Returns none for a path never written to."""
        with patch.object(fb.requests, "get", return_value=_response(200, None)):
            assert _client().get_file_text("ns/devices/phone/log.json") is None

    def test_raises_when_the_value_is_not_a_text_blob(self) -> None:
        """Raises when the value is not a text blob."""
        with (
            patch.object(fb.requests, "get", return_value=_response(200, {"a": 1})),
            pytest.raises(FirebaseSyncError, match="not the expected text blob"),
        ):
            _client().get_file_text("ns/devices/pc/log.json")

    @pytest.mark.parametrize("status", [401, 403])
    def test_raises_database_not_found_when_the_rules_reject(self, status: int) -> None:
        """Raises database not found when the rules reject."""
        with (
            patch.object(
                fb.requests, "get", return_value=_response(status, {"error": "denied"})
            ),
            pytest.raises(DatabaseNotFoundError),
        ):
            _client().get_file_text("ns/devices/pc/log.json")

    def test_raises_a_plain_sync_error_on_any_other_non_2xx(self) -> None:
        # Spark quota exhaustion lands here. It must surface, never be
        # swallowed into a None that reads as "nothing to sync".
        """Raises a plain sync error on any other non 2xx."""
        with (
            patch.object(
                fb.requests, "get", return_value=_response(429, {"error": "quota"})
            ),
            pytest.raises(FirebaseSyncError, match="429"),
        ):
            _client().get_file_text("ns/devices/pc/log.json")

    def test_turns_a_network_failure_into_a_sync_error(self) -> None:
        """Turns a network failure into a sync error."""
        with (
            patch.object(
                fb.requests, "get", side_effect=requests.ConnectionError("offline")
            ),
            pytest.raises(FirebaseSyncError, match="network error"),
        ):
            _client().get_file_text("ns/devices/pc/log.json")


class TestListDirectory:
    """List directory."""

    def test_returns_decoded_keys_and_asks_for_a_shallow_read(self) -> None:
        """Returns decoded keys and asks for a shallow read."""
        payload = {"pc": True, "phone": True}
        with patch.object(
            fb.requests, "get", return_value=_response(200, payload)
        ) as get_mock:
            assert _client().list_directory("ns/devices") == ["pc", "phone"]
        # shallow=true keeps a listing costing bytes instead of the whole
        # subtree -- the difference between ~40 MB/month and ~700 MB.
        assert get_mock.call_args.kwargs["params"]["shallow"] == "true"

    def test_decodes_escaped_filenames_back(self) -> None:
        # The notes app lists filenames, not device dirs: `.json` returns.
        """Decodes escaped filenames back."""
        with patch.object(
            fb.requests, "get", return_value=_response(200, {"abc~2Ejson": True})
        ):
            assert _client().list_directory("todo-sync/notes") == ["abc.json"]

    def test_returns_empty_for_an_unwritten_prefix(self) -> None:
        """Returns empty for an unwritten prefix."""
        with patch.object(fb.requests, "get", return_value=_response(200, None)):
            assert not _client().list_directory("ns/devices")

    def test_raises_on_a_non_2xx_response(self) -> None:
        """Raises on a non 2xx response."""
        with (
            patch.object(
                fb.requests, "get", return_value=_response(500, {"error": "boom"})
            ),
            pytest.raises(FirebaseSyncError),
        ):
            _client().list_directory("ns/devices")
