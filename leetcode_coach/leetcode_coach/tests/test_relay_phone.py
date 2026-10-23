"""The RTDB mirror and intake, against a recording stand-in for `Rtdb`."""

from __future__ import annotations

import json
import logging
import threading
from typing import TYPE_CHECKING, Any

import pytest

from leetcode_coach.relay import phone as phone_mod
from leetcode_coach.relay import sse
from leetcode_coach.relay.done import DAY_MS, DoneMap
from leetcode_coach.relay.lane import Lane
from leetcode_coach.relay.rtdb import RtdbError
from leetcode_coach.tests._relay_direct import FakeAsk, make_coach, started
from leetcode_coach.tests._relay_support import DEV, rid

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


class Recorder:
    """put/patch/delete/get kept in order; `fail` names calls that raise."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, object]] = []
        self.fail: set[str] = set()
        self.nodes: object = None
        self.events: list[sse.Event] = []

    def _do(self, method: str, path: str, value: object = None) -> None:
        if method in self.fail or f"{method} {path}" in self.fail:
            msg = f"{method} {path}: HTTP 503"
            raise RtdbError(msg)
        self.calls.append((method, path, value))

    def put(self, path: str, value: object) -> None:
        self._do("put", path, value)

    def patch(self, path: str, value: dict[str, object]) -> None:
        self._do("patch", path, value)

    def delete(self, path: str) -> None:
        self._do("delete", path)

    def get(self, path: str) -> object:
        self._do("get", path)
        return self.nodes

    def paths(self, method: str) -> list[str]:
        return [p for m, p, _v in self.calls if m == method]


@pytest.fixture
def link(tmp_path: Path) -> tuple[phone_mod.PhoneLink, Recorder, Lane]:
    coach = make_coach(tmp_path, FakeAsk([{"result": "Hi?"}]))
    now = [10 * DAY_MS]
    lane = Lane(
        coach.handle,
        DoneMap(tmp_path / "done.jsonl", lambda: now[0]),
        clock_ms=lambda: now[0],
    )
    rec = Recorder()
    made = phone_mod.PhoneLink(
        rec, lane, coach, lambda: {"version": 1}, clock_ms=lambda: now[0]
    )
    made.attach()
    return made, rec, lane


def _req(kind: str = "hint") -> dict[str, Any]:
    return {"kind": kind, "dev": DEV, "body": {"session": "20261023-170448-5b71"}}


def test_events_at_every_depth_reach_the_lane(link: Any) -> None:
    made, rec, lane = link
    a, b, c, d = rid(), rid(), rid(), rid()
    made.on_event(sse.Event("put", "/", {b: {"req": _req()}, a: {"req": _req()}}))
    made.on_event(sse.Event("put", f"/{c}", {"req": _req()}))
    made.on_event(sse.Event("patch", "/", {f"{d}/req": _req()}))
    made.on_event(sse.Event("put", f"/{a}/result", "ours"))
    made.on_event(sse.Event("put", "/", None))
    assert [r.rid for r in lane._queue] == [a, b, c, d]
    made.consider(rid(), {"req": [1]})  # not an object: no rid to answer under
    made.consider("bad", {"req": _req()})
    assert len(lane._queue) == 4
    made.consider(rid(), {"req": _req()})
    limited = rid()
    made.consider(limited, {"req": _req()})
    assert "rate_limited" in str(rec.calls[-1][2])
    assert rec.calls[-1][1] == f"requests/{limited}/result"
    assert rec.paths("put").count("heartbeat") == 1


def test_results_go_only_to_the_phone(link: Any) -> None:
    made, rec, _lane = link
    desktop = type("R", (), {"transport": "desktop", "rid": rid()})()
    made.on_result(desktop, {"ok": True})
    phone_req = type("R", (), {"transport": "phone", "rid": rid()})()
    made.on_result(phone_req, {"ok": True})
    puts = rec.paths("put")
    assert f"requests/{phone_req.rid}/result" in puts
    assert f"requests/{desktop.rid}/result" not in puts


def test_write_failures_are_logged_and_retried(
    link: Any, caplog: pytest.LogCaptureFixture
) -> None:
    made, rec, _lane = link
    coach = made.coach
    rec.fail = {"delete"}
    with caplog.at_level(logging.WARNING):
        started(coach)
    assert "RTDB chat reset failed" in caplog.text
    assert rec.paths("patch") == []
    rec.fail = {"patch"}
    made.on_state(coach.state(), coach.session)
    assert made._sent == set()
    rec.fail = set()
    made.on_state(coach.state(), coach.session)
    assert rec.calls[-2][0] == "patch"
    assert json.loads(str(rec.calls[0][2]))["schema"] == 1


def test_rescan_answers_and_cleans_up(
    link: Any, caplog: pytest.LogCaptureFixture
) -> None:
    made, rec, lane = link
    rec.fail = {"get"}
    made.rescan()
    assert "rescan failed" in caplog.text
    rec.fail = set()
    rec.nodes = "nope"
    made.rescan()
    old, fresh, lost, waiting = rid(), rid(), rid(), rid()
    lane.done.put(old, "phone", {"ok": True})
    lane._clock = lambda: 12 * DAY_MS
    lane.done._clock = lane._clock
    made._clock = lane._clock
    lane.done.put(fresh, "phone", {"ok": True})
    rec.nodes = {
        old: {"req": _req(), "result": "{}"},
        fresh: {"req": _req(), "result": "{}"},
        lost: {"req": _req(), "result": "{}"},
        waiting: {"req": _req()},
        "junk": 5,
    }
    made.rescan()
    assert sorted(rec.paths("delete")) == sorted(
        [f"requests/{old}", f"requests/{lost}"]
    )
    assert [r.rid for r in lane._queue] == [waiting]


def test_a_cancelled_stream_leaves_rescans(
    link: Any, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    made, _rec, _lane = link

    def cancelled(*_a: object) -> Iterator[sse.Event]:
        yield sse.Event("put", "/", None)
        msg = "rules"
        raise sse.StreamCancelledError(msg)

    monkeypatch.setattr(phone_mod.sse, "listen", cancelled)
    made.listen(threading.Event())
    assert "rescans only now" in caplog.text


def test_tend_beats_and_rescans_until_stopped(link: Any) -> None:
    made, rec, _lane = link
    stop = threading.Event()
    waits: list[float] = []

    def wait(seconds: float) -> None:
        waits.append(seconds)
        if len(waits) == 3:
            stop.set()

    made._beat_every, made._rescan_every = 1.0, 2.0
    made.tend(stop, wait)
    assert waits == [1.0, 1.0, 1.0]
    assert rec.paths("get") == ["requests", "requests"]
