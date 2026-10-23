"""SSE parsing and the reconnect-forever listener."""

from __future__ import annotations

import itertools
import threading
from typing import TYPE_CHECKING

import pytest

from leetcode_coach.relay import rtdb, sse
from leetcode_coach.tests._fake_rtdb import FakeRtdb

if TYPE_CHECKING:
    from collections.abc import Generator

Script = list[tuple[str, str] | Exception] | Exception


class ScriptedRtdb:
    """Each `stream` call plays the next connection: blocks, then EOF or a raise."""

    def __init__(self, *connections: Script, on_last: threading.Event) -> None:
        self.connections = list(connections)
        self.on_last = on_last
        self.opened = 0

    def stream(self, path: str) -> Generator[tuple[str, str]]:
        assert path == "requests"
        self.opened += 1
        script = self.connections.pop(0)
        if not self.connections:
            self.on_last.set()  # the listener stops after this connection
        if isinstance(script, Exception):
            raise script
        for item in script:
            if isinstance(item, Exception):
                raise item
            yield item


def put(path: str, data: object) -> tuple[str, str]:
    return "put", f'{{"path": "{path}", "data": {data}}}'


def run(*connections: Script) -> tuple[list[sse.Event], list[float], ScriptedRtdb]:
    stop = threading.Event()
    db = ScriptedRtdb(*connections, on_last=stop)
    sleeps: list[float] = []
    events = list(sse.listen(db, "requests", stop, sleeps.append))
    return events, sleeps, db


def test_parse_joins_data_lines_and_defaults_to_message() -> None:
    assert sse.parse(["event: put", 'data: {"a":', "data: 1}"]) == ("put", '{"a":\n1}')
    assert sse.parse([": comment", "id: 7", "data:x"]) == ("message", "x")


def test_put_and_patch_events_come_out_typed_and_noise_is_ignored() -> None:
    events, sleeps, _db = run(
        [
            ("keep-alive", "null"),
            put("/", "null"),
            ("patch", '{"path": "/R1", "data": {"req": 1}}'),
            ("rules_debug", "x"),
        ],
        [put("/", "{}")],
    )
    assert events == [
        sse.Event("put", "/", None),
        sse.Event("patch", "/R1", {"req": 1}),
        sse.Event("put", "/", {}),
    ]
    assert sleeps == []  # a connection that delivered events reconnects at once


def test_a_payload_without_a_path_is_at_the_root() -> None:
    events, _sleeps, _db = run([("put", '{"data": 5}')])
    assert events == [sse.Event("put", "/", 5)]


def test_auth_revoked_reconnects_at_once() -> None:
    events, sleeps, db = run([("auth_revoked", "null")], [put("/R2", '"x"')])
    assert events == [sse.Event("put", "/R2", "x")]
    assert (sleeps, db.opened) == ([], 2)


def test_cancel_is_fatal() -> None:
    stop = threading.Event()
    db = ScriptedRtdb([("cancel", "null")], [], on_last=threading.Event())
    with pytest.raises(sse.StreamCancelledError, match="cancelled"):
        list(sse.listen(db, "requests", stop, lambda _s: None))
    assert isinstance(sse.StreamCancelledError("x"), rtdb.RtdbError)


def test_failures_back_off_and_an_event_resets_the_count() -> None:
    boom = rtdb.RtdbError("STREAM requests: HTTP 503")
    events, sleeps, _db = run(
        boom,
        boom,
        [("put", "not json")],
        [("put", "[1, 2]")],
        [put("/", "1")],
        boom,
        [],
        *[boom] * 4,
        [],
    )
    assert events == [sse.Event("put", "/", 1)]
    assert sleeps == [1.0, 2.0, 5.0, 10.0, 1.0, 2.0, 5.0, 10.0, 30.0, 30.0]


def test_a_clean_close_with_no_event_backs_off() -> None:
    _events, sleeps, _db = run([], [], [])
    assert sleeps == [1.0, 2.0]  # the last close sees `stop` and never sleeps


def test_an_error_after_events_retries_from_the_shortest_delay() -> None:
    boom = rtdb.RtdbError("STREAM requests: ReadTimeout")
    events, sleeps, _db = run([put("/", "1"), boom], boom, [])
    assert events == [sse.Event("put", "/", 1)]
    assert sleeps == [1.0, 2.0]


def test_stop_ends_the_listener_after_the_current_event() -> None:
    stop = threading.Event()
    db = ScriptedRtdb([put("/", "1"), put("/", "2")], [], on_last=threading.Event())
    listener = sse.listen(db, "requests", stop, lambda _s: None)
    assert next(listener) == sse.Event("put", "/", 1)
    stop.set()
    assert list(listener) == []
    assert db.opened == 1


def test_an_already_stopped_listener_opens_nothing() -> None:
    stop = threading.Event()
    stop.set()
    db = ScriptedRtdb([], on_last=threading.Event())
    assert list(sse.listen(db, "requests", stop)) == []
    assert db.opened == 0


def test_the_default_sleep_waits_on_the_stop_event() -> None:
    stop = threading.Event()
    db = ScriptedRtdb(rtdb.RtdbError("down"), on_last=stop)
    assert (
        list(sse.listen(db, "requests", stop)) == []
    )  # stop.wait(1.0) returns at once


def test_against_the_fake_database_across_a_token_revocation() -> None:
    counter = itertools.count(1)
    with FakeRtdb.start() as fake:
        db = rtdb.Rtdb(fake.url, lambda: f"t{next(counter)}")
        stop = threading.Event()
        listener = sse.listen(db, "requests", stop, lambda _s: None)
        assert next(listener) == sse.Event("put", "/", None)
        fake.write("requests/R1/req", {"kind": "chat"})
        assert next(listener) == sse.Event("put", "/R1/req", {"kind": "chat"})
        fake.revoke_streams()
        assert next(listener) == sse.Event(
            "put", "/", {"R1": {"req": {"kind": "chat"}}}
        )
        assert fake.tokens[-1] == "t2"  # the reconnect asked for a fresh token
        fake.write("requests/R1/result", "ok")
        assert next(listener) == sse.Event("put", "/R1/result", "ok")
        stop.set()
        fake.write("requests/R2/req", {"kind": "hint"})
        assert list(listener) == []
