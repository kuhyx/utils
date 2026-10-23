"""A hanging Firebase never stalls the desktop; writes land in contract order."""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

from leetcode_coach.relay import outbox as outbox_mod
from leetcode_coach.relay.done import DoneMap
from leetcode_coach.relay.lane import Lane
from leetcode_coach.relay.phone import PhoneLink
from leetcode_coach.relay.rtdb import RtdbError
from leetcode_coach.tests._relay_direct import FakeAsk, make_coach, req

if TYPE_CHECKING:
    from pathlib import Path


class Stuck:
    """An RTDB whose writes hang until released, recording their order."""

    def __init__(self) -> None:
        self.release = threading.Event()
        self.calls: list[tuple[str, str]] = []

    def _hang(self, method: str, path: str) -> None:
        self.release.wait(10)
        self.calls.append((method, path))

    def put(self, path: str, _value: object) -> None:
        self._hang("put", path)

    def patch(self, path: str, _value: object) -> None:
        self._hang("patch", path)

    def delete(self, path: str) -> None:
        self._hang("delete", path)


def test_the_desktop_is_served_while_rtdb_hangs(tmp_path: Path) -> None:
    coach = make_coach(tmp_path, FakeAsk([{"result": "Hi?"}]))
    lane = Lane(
        coach.handle, DoneMap(tmp_path / "done.jsonl", lambda: 1), clock_ms=lambda: 1
    )
    rtdb = Stuck()
    link = PhoneLink(rtdb, lane, coach, lambda: {"version": 1}, clock_ms=lambda: 1)
    stop = threading.Event()
    writer = threading.Thread(target=link.outbox.run, args=(stop,))
    writer.start()
    link.attach()
    t0 = time.monotonic()
    started = coach.handle(req("session_start", slug="missing-number"))
    phone_req = req("hint", transport="phone", session=started["data"]["session"])
    link.on_result(phone_req, {"ok": True})
    assert started["ok"]
    assert time.monotonic() - t0 < 2  # never waited on the hanging writes
    rtdb.release.set()
    deadline = time.monotonic() + 5
    while link.outbox.pending() and time.monotonic() < deadline:
        time.sleep(0.01)
    stop.set()
    link.outbox.wake()
    writer.join(timeout=5)
    tail = rtdb.calls[-5:]
    assert tail == [
        ("delete", "chat"),
        ("patch", "chat"),
        ("put", "state"),
        ("put", "heartbeat"),
        ("put", f"requests/{phone_req.rid}/result"),
    ]


def test_a_failing_write_backs_off_and_a_stale_one_is_dropped() -> None:
    box = outbox_mod.Outbox()
    tries: list[str] = []

    def fail() -> None:
        tries.append("state-1")
        msg = "PUT state: HTTP 503"
        raise RtdbError(msg)

    box.put("state", fail, latest="state")
    assert not box.drain()
    assert box.pending() == ["state"]
    stop = threading.Event()
    pauses: list[float] = []

    def recovered() -> None:
        tries.append("state-2")
        stop.set()

    def pause(seconds: float) -> None:
        pauses.append(seconds)
        box.put("state", recovered, latest="state")

    box.run(stop, pause)
    assert pauses == [1.0]
    assert tries == ["state-1", "state-1", "state-2"]
    assert box.pending() == []

    def fail_then_newer() -> None:
        box.put("state", lambda: tries.append("state-3"), latest="state")
        msg = "PUT state: HTTP 503"
        raise RtdbError(msg)

    box.put("state", fail_then_newer, latest="state")
    assert not box.drain()
    assert box.pending() == ["state"]  # the failed, older one was dropped
    assert box.drain()
    assert tries[-1] == "state-3"


def test_an_idle_outbox_stops_on_wake() -> None:
    box = outbox_mod.Outbox()
    stop = threading.Event()
    runner = threading.Thread(target=box.run, args=(stop,))
    runner.start()
    stop.set()
    box.wake()
    runner.join(timeout=2)
    assert not runner.is_alive()
