"""Write the Python half of the live cross-language interop check.

``crdt_sync_dart/tool/interop_check.dart`` merges a Dart record into
``_interop/devices`` and then asserts it can also see a record written by the
*Python* client -- but nothing wrote that record, so the check could only ever
fail. This is the missing half: it pushes ``py-rec`` through the real
:class:`FirebaseSyncClient`, so the Dart tool has something to find.

The two implementations must agree byte-for-byte, or a phone running Dart
would silently not see a PC running Python. That is the failure this pair of
tools exists to catch before any real data depends on it.

Run this first, then the Dart checker::

    python3 tool/interop_seed.py
    dart run tool/interop_check.dart

Writes only under ``_interop/``; the Dart side deletes both devices' data on
its way out.
"""

from __future__ import annotations

import logging
import sys

from crdt_sync import (
    FirebaseConfig,
    Hlc,
    MemorySyncStateStore,
    Record,
    dump_log,
    firebase_client_for,
    load_log,
    sync_log,
)

_PATH_PREFIX = "_interop/devices"
_DEVICE_ID = "pydev"

_logger = logging.getLogger("interop-seed")


# The library's canonical serializers, deliberately -- the point of the check
# is that what the real apps write is what the other language reads, so
# reimplementing the encoding here would test the wrong thing.


def main() -> int:
    """Push the Python-side record, returning a process exit code."""
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")

    client = firebase_client_for("interop", config=FirebaseConfig.load())
    merged = sync_log(
        client=client,
        device_id=_DEVICE_ID,
        path_prefix=_PATH_PREFIX,
        local_log={
            "py-rec": Record(
                id="py-rec",
                fields={
                    "value": (
                        "written-by-python",
                        Hlc(wall_time_ms=1000, counter=0, node_id="node-py"),
                    )
                },
            )
        },
        encode=dump_log,
        decode=load_log,
        state_store=MemorySyncStateStore(),
    )

    _logger.info("python sees records: %s", sorted(merged))
    _logger.info("seeded %s; now run: dart run tool/interop_check.dart", _DEVICE_ID)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
