"""The paced serial lane and the done-map (DOCS-coach-relay.md section 1)."""

from __future__ import annotations

import json
import logging
import threading
from typing import TYPE_CHECKING, Any

from leetcode_coach.relay import done as done_mod
from leetcode_coach.relay import lane as lane_mod
from leetcode_coach.relay import protocol

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _rid(n: int) -> str:
    return f"01JAXY{n:020d}"


def _req(n: int, transport: str = "desktop") -> protocol.Request:
    return protocol.Request(_rid(n), "hint", "dev", {"session": "s"}, transport)


class Clock:
    def __init__(self) -> None:
        self.ms = 1_000_000
        self.mono = 100.0

    def now_ms(self) -> int:
        return self.ms

    def monotonic(self) -> float:
        return self.mono


def test_the_done_map_survives_a_restart_and_expires(tmp_path: Path) -> None:
    clock = Clock()
    path = tmp_path / "relay" / "requests_done.jsonl"
    done = done_mod.DoneMap(path, clock.now_ms)
    done.put(_rid(1), "phone", {"ok": True})
    done.put(_rid(2), "desktop", {"ok": False})
    again = done_mod.DoneMap(path, clock.now_ms)
    assert again.get(_rid(1)) == done_mod.Done(_rid(1), clock.ms, "phone", {"ok": True})
    clock.ms += done_mod.DAY_MS + 1
    assert again.get(_rid(2)) is None
    assert again.get(_rid(1)) is not None
    assert again.get(_rid(3)) is None
    clock.ms += done_mod.KEEP_MS
    assert again.get(_rid(1)) is None
    done_mod.DoneMap(path, clock.now_ms)
    assert path.read_text(encoding="utf-8") == ""


def test_a_torn_done_map_line_is_skipped(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "done.jsonl"
    good = {"rid": _rid(1), "at": 5, "transport": "phone", "result": {"ok": True}}
    path.write_text(f'{json.dumps(good)}\n{{"rid": \n\n[1]\n', encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        done = done_mod.DoneMap(path, lambda: 10)
    assert done.get(_rid(1)) is not None
    assert caplog.text.count("done-map line skipped") == 2
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1


def _lane(tmp_path: Path, handle: Any, clock: Clock, **kw: Any) -> lane_mod.Lane:
    done = done_mod.DoneMap(tmp_path / "done.jsonl", clock.now_ms)
    return lane_mod.Lane(
        handle, done, clock_ms=clock.now_ms, monotonic=clock.monotonic, **kw
    )


def test_fifo_paced_and_capped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = Clock()
    lane = _lane(tmp_path, lambda r: {"ok": True, "rid": r.rid}, clock)
    assert all(lane.submit(_req(n)) is None for n in range(5))
    assert lane.submit(_req(0)) is None  # a resend of a queued rid
    limited = lane.submit(_req(9))
    assert limited is not None
    assert limited["code"] == "rate_limited"
    assert limited["retry"] is True
    assert limited["retry_after_ms"] == 15000
    assert lane.result(_rid(9)) == limited
    assert lane.submit(_req(9)) == limited
    assert lane.known(_rid(4))
    assert not lane.known(_rid(7))
    stop = threading.Event()
    starts: list[str | None] = []
    lane.on_busy.append(starts.append)
    seen: list[str] = []
    lane.on_result.append(lambda req, _res: seen.append(req.rid))
    assert lane._next(stop) == _req(0)
    assert lane.busy == _rid(0)
    assert lane.submit(_req(0)) is None  # running: still not re-run
    lane.busy = None

    def advance(_timeout: float | None = None) -> bool:
        clock.mono += 3.0
        return True

    monkeypatch.setattr(lane._cv, "wait", advance)  # the clock moves per wait
    for n in range(1, 5):
        assert lane._next(stop) == _req(n)
        lane.busy = None
    stop.set()
    assert lane._next(stop) is None


def test_the_worker_runs_until_stopped_and_records_results(tmp_path: Path) -> None:
    clock = Clock()
    stop = threading.Event()

    def handle(req: protocol.Request) -> dict[str, Any]:
        if req.rid == _rid(2):
            stop.set()
        if req.rid == _rid(1):
            message = "boom"
            raise RuntimeError(message)
        return {"ok": True}

    lane = _lane(tmp_path, handle, clock, pace_s=0.0)
    results: list[tuple[str, dict[str, Any]]] = []
    lane.on_result.append(lambda req, res: results.append((req.rid, res)))
    busy: list[str | None] = []
    lane.on_busy.append(busy.append)
    for n in range(3):
        lane.submit(_req(n))
    lane.run(stop)
    assert [rid for rid, _ in results] == [_rid(0), _rid(1), _rid(2)]
    assert busy == [_rid(0), None, _rid(1), None, _rid(2), None]
    assert results[1][1]["code"] == "worker_error"
    assert lane.result(_rid(0)) == {"ok": True}
    assert lane.known(_rid(3)) is False
    lane.stop()


def test_an_idle_lane_stops(tmp_path: Path) -> None:
    clock = Clock()
    lane = _lane(tmp_path, lambda _r: {}, clock)
    stop = threading.Event()
    worker = threading.Thread(target=lane.run, args=(stop,))
    worker.start()
    stop.set()
    lane.stop()
    worker.join(timeout=2)
    assert not worker.is_alive()
