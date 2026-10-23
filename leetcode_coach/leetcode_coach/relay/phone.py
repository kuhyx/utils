"""The phone's path: RTDB requests in, results/state/chat/heartbeat out.

Under ``leetcode-guard/coach/`` (DOCS-coach-relay.md 1). Requests arrive over
an SSE stream of ``requests`` and, as a backstop, a rescan every
`RESCAN_S` and at start-up; both go through `consider`, which answers a rid
the done-map knows from the map (re-PUT, never re-run) and queues the rest
on the shared lane. Results, ``state`` (a JSON string leaf) and the chat
lines are written as they change; the heartbeat every `HEARTBEAT_S` and on
every ``rev`` or busy change. ``requests/{rid}`` goes 24 h after its result.

Firebase being down never stops the relay: every write failure is logged
and the next change or beat tries again; the desktop keeps being served.
"""

from __future__ import annotations

import functools
import json
import logging
import threading
from typing import TYPE_CHECKING, Any, Final

from leetcode_coach.relay import protocol, sse
from leetcode_coach.relay.done import DAY_MS
from leetcode_coach.relay.rtdb import SERVER_TIME, RtdbError

if TYPE_CHECKING:
    from collections.abc import Callable

    from leetcode_coach.relay.coach import Coach
    from leetcode_coach.relay.lane import Lane
    from leetcode_coach.relay.rtdb import Rtdb
    from leetcode_coach.relay.session import Session

_logger: Final = logging.getLogger(__name__)

_REQ_DEPTH: Final = 2
"""``{rid}/req``: a path two segments deep."""

HEARTBEAT_S: Final = 30.0
RESCAN_S: Final = 60.0


def _pairs(event: sse.Event) -> list[tuple[list[str], object]]:
    """``(path segments, value)`` for every node an event set."""
    base = [s for s in event.path.split("/") if s]
    if event.kind == "patch" and isinstance(event.data, dict):
        return [
            (base + [s for s in str(k).split("/") if s], v)
            for k, v in event.data.items()
        ]
    return [(base, event.data)]


class PhoneLink:
    """Mirrors the relay into RTDB and feeds RTDB requests to the lane."""

    def __init__(  # pylint: disable=too-many-arguments
        self,
        rtdb: Rtdb,
        lane: Lane,
        coach: Coach,
        heartbeat: Callable[[], dict[str, Any]],
        *,
        clock_ms: Callable[[], int],
        heartbeat_s: float = HEARTBEAT_S,
        rescan_s: float = RESCAN_S,
    ) -> None:
        """Bind the database and the relay; call `attach` to start mirroring."""
        self.rtdb = rtdb
        self.lane = lane
        self.coach = coach
        self._heartbeat = heartbeat
        self._clock = clock_ms
        self._beat_every = heartbeat_s
        self._rescan_every = rescan_s
        self._write_lock = threading.Lock()
        self._chat_sid: str | None = None
        self._sent: set[str] = set()

    def _write(self, what: str, call: Callable[[], None]) -> bool:
        with self._write_lock:
            try:
                call()
            except RtdbError as exc:
                _logger.warning("RTDB %s failed: %s", what, exc)
                return False
        return True

    def attach(self) -> None:
        """Listen to the lane and the backend; then mirror everything once."""
        self.lane.on_result.append(self.on_result)
        self.lane.on_busy.append(lambda _busy: self.beat())
        self.coach.listeners.append(self.on_state)
        self._chat_sid = None
        self.on_state(self.coach.state(), self.coach.session)

    def beat(self) -> None:
        """PUT the heartbeat (``beat`` as a server timestamp)."""
        beat = {**self._heartbeat(), "beat": SERVER_TIME}
        self._write("heartbeat", lambda: self.rtdb.put("heartbeat", beat))

    def put_result(self, rid: str, result: dict[str, Any]) -> None:
        """``requests/{rid}/result`` as a JSON string leaf."""
        text = json.dumps(result, ensure_ascii=False)
        self._write("result", lambda: self.rtdb.put(f"requests/{rid}/result", text))

    def on_result(self, req: protocol.Request, result: dict[str, Any]) -> None:
        """A finished request: answer it if it came from the phone."""
        if req.transport == "phone":
            self.put_result(req.rid, result)

    def on_state(self, state: dict[str, Any], session: Session | None) -> None:
        """Mirror ``state``, the new chat lines and the heartbeat."""
        text = json.dumps(state, ensure_ascii=False)
        self._write("state", lambda: self.rtdb.put("state", text))
        sid = None if session is None else session.sid
        if sid != self._chat_sid and self._write(
            "chat reset", lambda: self.rtdb.delete("chat")
        ):
            self._chat_sid, self._sent = sid, set()
        if session is not None and sid == self._chat_sid:
            new: dict[str, object] = {
                k: v for k, v in session.chat.items() if k not in self._sent
            }
            if new and self._write("chat", lambda: self.rtdb.patch("chat", new)):
                self._sent |= set(new)
        self.beat()

    def consider(self, rid: str, node: object) -> None:
        """One ``requests/{rid}`` node: answer, queue, or leave it."""
        if not isinstance(node, dict) or "req" not in node or "result" in node:
            return
        if not protocol.RID_RE.fullmatch(rid):
            _logger.warning("phone request with a bad rid ignored")
            return
        if (done := self.lane.done.get(rid)) is not None:
            self.put_result(rid, done.result)
            return
        raw = node["req"]
        try:
            req = protocol.parse(
                {**raw, "rid": rid} if isinstance(raw, dict) else raw, "phone"
            )
        except protocol.BadRidError as exc:
            _logger.warning("phone request %s refused: %s", rid, exc)
            return
        except protocol.BadRequestError as exc:
            _logger.warning("bad phone request %s: %s", rid, exc)
            result = protocol.failure("bad_request", str(exc), at=self._clock())
            self.lane.finish(rid, "phone", result)
            self.put_result(rid, result)
            return
        if (immediate := self.lane.submit(req)) is not None:
            self.put_result(rid, immediate)

    def on_event(self, event: sse.Event) -> None:
        """Route one SSE event under ``requests``."""
        for segs, value in _pairs(event):
            if not segs and isinstance(value, dict):
                for rid in sorted(value):
                    self.consider(str(rid), value[rid])
            elif len(segs) == 1:
                self.consider(segs[0], value)
            elif len(segs) == _REQ_DEPTH and segs[1] == "req":
                self.consider(segs[0], {"req": value})

    def rescan(self) -> None:
        """Pick up anything the stream missed; drop answered nodes after 24 h."""
        try:
            nodes = self.rtdb.get("requests")
        except RtdbError as exc:
            _logger.warning("RTDB rescan failed: %s", exc)
            return
        if not isinstance(nodes, dict):
            return
        now = self._clock()
        for rid in sorted(nodes):
            node = nodes[rid]
            self.consider(str(rid), node)
            if not isinstance(node, dict) or "result" not in node:
                continue
            done = self.lane.done.get(str(rid))
            if done is None or now - done.at > DAY_MS:
                drop = functools.partial(self.rtdb.delete, f"requests/{rid}")
                self._write("cleanup", drop)

    def listen(self, stop: threading.Event) -> None:
        """The SSE loop; a cancelled stream leaves the rescans to carry on."""
        try:
            for event in sse.listen(self.rtdb, "requests", stop):
                self.on_event(event)
        except sse.StreamCancelledError:
            _logger.exception("the requests stream was cancelled; rescans only now")

    def tend(self, stop: threading.Event, wait: Callable[[float], object]) -> None:
        """Heartbeat every 30 s, rescan every 60 s, until `stop`."""
        since_scan = self._rescan_every
        while not stop.is_set():
            if since_scan >= self._rescan_every:
                self.rescan()
                since_scan = 0.0
            self.beat()
            wait(self._beat_every)
            since_scan += self._beat_every
