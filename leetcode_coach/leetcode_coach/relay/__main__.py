"""``python3 -m leetcode_coach.relay``: the systemd unit's entry point.

Logs to stderr (the journal) at INFO; SIGTERM stops taking requests and
lets the running one finish (the unit's ``KillMode=mixed`` spares the claude
child meanwhile). The phone path signs in as crdt_sync app
``leetcode_coach_relay`` via `_snapshot_auth.connect`, which heals from a
sibling app's session; ``$LEETCODE_COACH_RTDB_URL`` skips sign-in (tests).
"""

from __future__ import annotations

import logging
import signal
import sys
import threading

from crdt_sync import CONFIG_FILE, FirebaseConfig

from leetcode_coach.relay import config
from leetcode_coach.relay.app import Relay
from leetcode_coach.relay.coach import Deps
from leetcode_coach.relay.rtdb import Rtdb
from leetcode_guard import _snapshot_auth

FAKE_ID = "relay-test"
"""What the relay hands the fake RTDB, which takes any non-empty id token."""


def make_rtdb() -> Rtdb:
    """The signed-in RTDB client (or the fake one the env var names)."""
    url = config.rtdb_url()
    if url:
        return Rtdb(url, lambda: FAKE_ID)
    client = _snapshot_auth.connect(config.APP_NAME, timeout_seconds=15)
    database = FirebaseConfig.load(CONFIG_FILE).database_url
    return Rtdb(database, client.auth.id_token)


def main() -> int:
    """Run until SIGTERM / SIGINT."""
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
    )
    relay = Relay(Deps())

    def stop(_signum: int, _frame: object) -> None:
        relay.stop_event.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    relay.start()
    logging.getLogger(__name__).info("coach relay on 127.0.0.1:%d", relay.port)
    threading.Thread(
        target=relay.connect_phone, args=(make_rtdb,), name="rtdb", daemon=True
    ).start()
    relay.stop_event.wait()
    relay.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
