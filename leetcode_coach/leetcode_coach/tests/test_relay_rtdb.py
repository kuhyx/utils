"""The relay's RTDB REST client, against the in-process fake database."""

from __future__ import annotations

import itertools
import json
from typing import TYPE_CHECKING, Any

import pytest
import requests

from leetcode_coach.relay import rtdb
from leetcode_coach.tests._fake_rtdb import NOW_MS, FakeRtdb

if TYPE_CHECKING:
    from collections.abc import Iterator

SECRET = "tok-secret"


@pytest.fixture
def fake() -> Iterator[FakeRtdb]:
    with FakeRtdb.start() as db:
        yield db


def client(fake: FakeRtdb, **kwargs: Any) -> rtdb.Rtdb:
    counter = itertools.count(1)
    return rtdb.Rtdb(fake.url, lambda: f"{SECRET}-{next(counter)}", **kwargs)


def test_url_quotes_each_segment_under_the_coach_root() -> None:
    db = rtdb.Rtdb("https://x.firebaseio.com/", lambda: "t")
    assert db.url("requests/01AB/result") == (
        "https://x.firebaseio.com/leetcode-guard/coach/requests/01AB/result.json"
    )
    assert (
        db.url("/a b//c/")
        == "https://x.firebaseio.com/leetcode-guard/coach/a%20b/c.json"
    )
    assert db.url("") == "https://x.firebaseio.com/leetcode-guard/coach.json"


def test_put_and_get_a_json_string_leaf(fake: FakeRtdb) -> None:
    db = client(fake)
    db.put("state", json.dumps({"schema": 1, "steps": []}))
    assert fake.read("state") == '{"schema": 1, "steps": []}'
    assert db.get("state") == '{"schema": 1, "steps": []}'
    method, path, query = fake.requests[0]
    assert (method, path) == ("PUT", "/leetcode-guard/coach/state.json")
    assert "print=silent" in query


def test_get_of_a_missing_node_is_none(fake: FakeRtdb) -> None:
    assert client(fake).get("requests") is None


def test_server_timestamps_resolve(fake: FakeRtdb) -> None:
    client(fake).put("heartbeat", {"beat": rtdb.SERVER_TIME, "version": 1})
    assert fake.read("heartbeat") == {"beat": NOW_MS, "version": 1}


def test_patch_merges_children_and_nested_keys(fake: FakeRtdb) -> None:
    db = client(fake)
    db.patch("chat", {"m0001": {"role": "coach", "text": "hi"}})
    db.patch("chat", {"m0002": {"role": "kuhy", "text": "yo"}, "m0001/text": "hey"})
    assert fake.read("chat") == {
        "m0001": {"role": "coach", "text": "hey"},
        "m0002": {"role": "kuhy", "text": "yo"},
    }
    assert "print=silent" in fake.requests[-1][2]


def test_delete_removes_the_node_and_prunes_empty_parents(fake: FakeRtdb) -> None:
    db = client(fake)
    db.put("requests/R1/result", '"done"')
    db.delete("requests/R1")
    assert fake.read("requests") is None
    assert fake.read() is None


def test_every_call_asks_for_a_fresh_token(fake: FakeRtdb) -> None:
    db = client(fake)
    db.get("a")
    db.get("b")
    assert fake.tokens == [f"{SECRET}-1", f"{SECRET}-2"]


def test_an_http_error_names_method_path_and_status_only(fake: FakeRtdb) -> None:
    fake.fail_next(1, status=401)
    with pytest.raises(rtdb.RtdbError) as caught:
        client(fake).put("state", "x")
    assert str(caught.value) == "PUT state: HTTP 401"


def test_a_network_error_never_leaks_the_url_or_token() -> None:
    db = rtdb.Rtdb("http://127.0.0.1:9", lambda: SECRET, timeout_s=2.0)
    with pytest.raises(rtdb.RtdbError) as caught:
        db.get("requests")
    assert str(caught.value) == "GET requests: ConnectionError"
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__


class _CannedSession(requests.Session):
    """Answers every request with one canned response (or raises)."""

    def __init__(self, response: requests.Response) -> None:
        super().__init__()
        self.response = response

    def request(self, *args: Any, **kwargs: Any) -> requests.Response:
        return self.response

    def get(self, *args: Any, **kwargs: Any) -> requests.Response:
        return self.response


def _response(status: int, body: bytes) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = body
    return response


def test_a_get_whose_body_is_not_json_is_an_error() -> None:
    db = rtdb.Rtdb(
        "http://x", lambda: "t", session=_CannedSession(_response(200, b"<html>"))
    )
    with pytest.raises(rtdb.RtdbError, match=r"^GET state: not JSON$"):
        db.get("state")


def test_stream_starts_with_the_whole_node_then_reports_writes(fake: FakeRtdb) -> None:
    fake.write("requests/R0/req", {"kind": "chat"})
    lines = client(fake).stream("requests")
    kind, data = next(lines)
    assert kind == "put"
    assert json.loads(data) == {"path": "/", "data": {"R0": {"req": {"kind": "chat"}}}}
    fake.write("requests/R1/req", {"kind": "hint", "created": {".sv": "timestamp"}})
    kind, data = next(lines)
    assert (kind, json.loads(data)) == (
        "put",
        {"path": "/R1/req", "data": {"kind": "hint", "created": NOW_MS}},
    )
    fake.revoke_streams()
    assert next(lines)[0] == "auth_revoked"
    assert list(lines) == []


def test_stream_http_error(fake: FakeRtdb) -> None:
    fake.fail_next(1, status=503)
    with pytest.raises(rtdb.RtdbError, match=r"^STREAM requests: HTTP 503$"):
        next(client(fake).stream("requests"))


def test_stream_connect_error() -> None:
    db = rtdb.Rtdb("http://127.0.0.1:9", lambda: SECRET)
    with pytest.raises(rtdb.RtdbError, match=r"^STREAM requests: ConnectionError$"):
        next(db.stream("requests"))


class _DyingResponse(requests.Response):
    """Delivers one block, then the connection drops mid-read."""

    def __init__(self) -> None:
        super().__init__()
        self.status_code = 200
        self.closed_by_client = False

    def iter_lines(self, *args: Any, **kwargs: Any) -> Iterator[bytes]:
        yield b""  # a stray blank line before any field is no block
        yield b"event: keep-alive"
        yield b"data: null"
        yield b""
        raise requests.exceptions.ChunkedEncodingError

    def close(self) -> None:
        self.closed_by_client = True


def test_a_drop_mid_stream_is_an_rtdb_error_and_closes_the_response() -> None:
    response = _DyingResponse()
    db = rtdb.Rtdb("http://x", lambda: "t", session=_CannedSession(response))
    lines = db.stream("requests")
    assert next(lines) == ("keep-alive", "null")
    with pytest.raises(
        rtdb.RtdbError, match=r"^STREAM requests: ChunkedEncodingError$"
    ):
        next(lines)
    assert response.closed_by_client


def test_stream_reports_patches_deletes_and_writes_above_the_node(
    fake: FakeRtdb,
) -> None:
    db = client(fake)
    lines = db.stream("requests")
    assert json.loads(next(lines)[1])["data"] is None
    db.patch("requests", {"R1/req": {"kind": "chat"}})
    assert json.loads(next(lines)[1]) == {
        "path": "/",
        "data": {"R1/req": {"kind": "chat"}},
    }
    db.delete("requests/R1")
    assert json.loads(next(lines)[1]) == {"path": "/R1", "data": None}
    db.put("", {"requests": {"R2": {"req": 1}}})
    assert json.loads(next(lines)[1]) == {"path": "/", "data": {"R2": {"req": 1}}}
    lines.close()
