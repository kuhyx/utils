"""Dev harness: the real relay on loopback, every outside dependency faked.

``python3 -m leetcode_coach.tests._live_relay PORT DIR [PACE_S]`` serves the
real `Relay` (lane, backend, HTTP API, phone mirror) on ``127.0.0.1:PORT``
so the app's own transport can be driven against it
(``app/tool/coach_live_check.sh``). Faked, so nothing real is read or
written: claude (``LEETCODE_CLAUDE_BIN``, set by the caller), the statement
fetch, the LeetCode Accepted probe, Anki (dry run), Ollama (the discard
port) and Firebase (an in-process `FakeRtdb`). Session logs and the relay's
own files go under ``DIR``. Writes ``DIR/ready`` once listening and runs
until SIGTERM / SIGINT.
"""

from __future__ import annotations

import os
from pathlib import Path
import signal
import sys

from leetcode_coach import local_backend, progress
from leetcode_coach.relay.app import Relay
from leetcode_coach.relay.coach import Deps
from leetcode_coach.relay.probe import AcceptedProbe
from leetcode_coach.relay.rtdb import Rtdb
from leetcode_coach.tests._fake_rtdb import FakeRtdb
from leetcode_coach.tests._relay_statements import MISSING_NUMBER
from leetcode_coach.tests._relay_support import FakeProbe

DEAD_OLLAMA = "http://127.0.0.1:9"
REAL_PORT = 8777
WITH_PACE = 3
USAGE = "usage: _live_relay PORT DIR [PACE_S]"


def main(argv: list[str]) -> int:
    """Serve until a signal; 2 on bad arguments."""
    if len(argv) not in {WITH_PACE - 1, WITH_PACE} or not argv[0].isdigit():
        sys.stderr.write(USAGE + "\n")
        return 2
    port, root = int(argv[0]), Path(argv[1])
    if port == REAL_PORT:
        sys.stderr.write("refusing the real relay's port\n")
        return 2
    pace = float(argv[2]) if len(argv) == WITH_PACE else 3.0
    os.environ[progress.SESSIONS_ENV] = str(root / "sessions")
    local_backend.OLLAMA_URL = DEAD_OLLAMA
    deps = Deps(
        state_dir=root / "relay",
        fetch=lambda _slug: ("Missing Number", MISSING_NUMBER),
        probe=AcceptedProbe(FakeProbe()),
        cards_dry_run=True,
    )
    relay = Relay(deps, port=port, pace_s=pace)
    fake = FakeRtdb.start()
    signal.signal(signal.SIGTERM, lambda *_: relay.stop_event.set())
    signal.signal(signal.SIGINT, lambda *_: relay.stop_event.set())
    relay.start()
    relay.link_phone(Rtdb(fake.url, lambda: "live-check"))
    (root / "ready").write_text(str(relay.port), encoding="utf-8")
    relay.stop_event.wait()
    relay.stop()
    fake.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
