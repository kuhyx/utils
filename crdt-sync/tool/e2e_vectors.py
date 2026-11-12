# Copyright (c) 2026 Krzysztof Rudnicki
"""Write golden vectors sealed by Python for the Dart side to open.

Run from ``crdt-sync``::

    python -m tool.e2e_vectors > e2e_py_vectors.json

then move the file to ``crdt_sync_dart/test/fixtures/``.
"""

from __future__ import annotations

import json
import sys

from crdt_sync import Argon2Params, seal_log_text, unlock_e2e
from crdt_sync.tests.conftest import FakeStore

# A public test-vector passphrase, not a secret.
PHRASE = "correct horse \u2713"


def vectors() -> dict[str, object]:
    """Return a fresh vector set (random salt and nonces)."""
    remote = FakeStore()
    key = unlock_e2e(
        remote,
        path_prefix="vec/notes-e2e",
        passphrase=PHRASE,
        params=Argon2Params(64, 2, 1),
        e2e_path="vec/e2e",
    )
    path = "vec/notes-e2e/pc/log.json"
    log = json.dumps(
        {
            "n9": {
                "id": "n9",
                "fields": {"title": ["zażółć", "2026-01-01T00:00:00.000Z-0000-pc"]},
                "deleted": False,
                "deleted_hlc": None,
            }
        },
        ensure_ascii=False,
    )
    cipher = key.cipher()
    return {
        "passphrase": PHRASE,
        "header": remote.files["vec/e2e"],
        "master_hex": key.master.hex(),
        "path": path,
        "log": log,
        "envelope": seal_log_text(log, cipher, path=path),
        "whole": seal_log_text("not a log", cipher, path=path),
    }


def main() -> int:
    """Print the vectors as JSON."""
    sys.stdout.write(json.dumps(vectors(), indent=2, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
