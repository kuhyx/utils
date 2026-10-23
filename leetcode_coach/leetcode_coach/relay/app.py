"""The relay assembled: backend, lane, loopback API, phone link, ticker.

One process (``leetcode-coach-relay.service``). Every wait is injectable so
the end-to-end tests run the real threads at test speed: the 3 s pace, the
Accepted ticker, the heartbeat and the rescan. The phone link connects in
its own thread and retries with backoff, so a Firebase outage at boot never
delays the desktop.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any, Final

from leetcode_coach.relay import config
from leetcode_coach.relay.coach import Coach, Deps
from leetcode_coach.relay.done import DoneMap
from leetcode_coach.relay.http_api import Server
from leetcode_coach.relay.lane import PACE_S, Lane
from leetcode_coach.relay.phone import HEARTBEAT_S, RESCAN_S, PhoneLink

if TYPE_CHECKING:
    from collections.abc import Callable

    from leetcode_coach.relay.rtdb import Rtdb

_logger: Final = logging.getLogger(__name__)

TICK_S: Final = 5.0
CONNECT_BACKOFF_S: Final = (5.0, 30.0, 120.0, 300.0)


class Relay:  # pylint: disable=too-many-instance-attributes
    """All the parts, and the threads that run them."""

    def __init__(  # pylint: disable=too-many-arguments
        self,
        deps: Deps,
        *,
        port: int | None = None,
        pace_s: float = PACE_S,
        tick_s: float = TICK_S,
        heartbeat_s: float = HEARTBEAT_S,
        rescan_s: float = RESCAN_S,
    ) -> None:
        """Build everything and bind the port; nothing runs until `start`."""
        self.deps = deps
        self.started = deps.clock_ms()
        self.coach = Coach(deps)
        done = DoneMap(deps.state_dir / "requests_done.jsonl", deps.clock_ms)
        self.lane = Lane(self.coach.handle, done, clock_ms=deps.clock_ms, pace_s=pace_s)
        bind = config.port() if port is None else port
        self.server = Server((config.HOST, bind), self)
        self.stop_event = threading.Event()
        self.phone: PhoneLink | None = None
        self._tick_s = tick_s
        self._beat_s = heartbeat_s
        self._rescan_s = rescan_s
        self._threads: list[threading.Thread] = []

    @property
    def port(self) -> int:
        """The bound loopback port (tests bind port 0)."""
        return int(self.server.server_address[1])

    def heartbeat(self) -> dict[str, Any]:
        """``{"beat", "started", "state_rev", "busy"?, "version"}`` (beat in ms)."""
        beat: dict[str, Any] = {
            "beat": self.deps.clock_ms(),
            "started": self.started,
            "state_rev": self.coach.rev,
            "version": 1,
        }
        if self.lane.busy is not None:
            beat["busy"] = self.lane.busy
        return beat

    def _spawn(self, name: str, target: Callable[[], object]) -> None:
        thread = threading.Thread(target=target, name=name, daemon=True)
        thread.start()
        self._threads.append(thread)

    def _tick_loop(self) -> None:
        while not self.stop_event.wait(self._tick_s):
            self.coach.tick()

    def start(self) -> None:
        """Serve the API, run the lane and the Accepted ticker."""
        self._spawn("http", self.server.serve_forever)
        self._spawn("lane", lambda: self.lane.run(self.stop_event))
        self._spawn("tick", self._tick_loop)

    def link_phone(self, rtdb: Rtdb) -> PhoneLink:
        """Mirror into `rtdb` and take the phone's requests from it."""
        phone = PhoneLink(
            rtdb,
            self.lane,
            self.coach,
            self.heartbeat,
            clock_ms=self.deps.clock_ms,
            heartbeat_s=self._beat_s,
            rescan_s=self._rescan_s,
        )
        phone.attach()
        self.phone = phone
        self._spawn("rtdb-listen", lambda: phone.listen(self.stop_event))
        self._spawn(
            "rtdb-tend", lambda: phone.tend(self.stop_event, self.stop_event.wait)
        )
        return phone

    def connect_phone(self, make: Callable[[], Rtdb]) -> None:
        """Keep trying `make` (Firebase sign-in) with backoff, then link."""
        failures = 0
        while not self.stop_event.is_set():
            try:
                rtdb = make()
            except Exception:  # pylint: disable=broad-exception-caught
                # Sign-in fails a dozen ways (config, auth, network); each is
                # an outage to wait out, never a reason to stop the relay.
                delay = CONNECT_BACKOFF_S[min(failures, len(CONNECT_BACKOFF_S) - 1)]
                failures += 1
                _logger.exception(
                    "RTDB not reachable; phone path retries in %.0fs", delay
                )
                self.stop_event.wait(delay)
                continue
            self.link_phone(rtdb)
            return

    def stop(self) -> None:
        """Stop taking requests, let the running one finish, close the port."""
        self.stop_event.set()
        self.lane.stop()
        if any(t.name == "http" for t in self._threads):
            self.server.shutdown()  # blocks unless serve_forever runs
        self.server.server_close()
        for thread in self._threads:
            if thread.name == "lane":
                thread.join(timeout=300)
