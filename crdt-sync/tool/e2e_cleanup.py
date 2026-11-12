# Copyright (c) 2026 Krzysztof Rudnicki
"""Clear an app's old plaintext RTDB prefix after the E2E copy is verified.

Dry run by default; ``--apply`` deletes. Run only once every device runs an
encrypting build::

    python3 -m tool.e2e_cleanup todo-sync/notes --app todo
    python3 -m tool.e2e_cleanup todo-sync/notes --app todo --apply
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

from crdt_sync import (
    PASSWORD_FILE,
    E2eLockedError,
    FirebaseConfig,
    clear_plaintext_prefix,
    firebase_client_for,
)

if TYPE_CHECKING:
    from crdt_sync import RemoteStore


def run(store: RemoteStore, old_prefix: str, passphrase: str, *, apply: bool) -> int:
    """Clear (or list) ``old_prefix``; return a process exit code."""
    try:
        paths = clear_plaintext_prefix(
            store, old_prefix, passphrase=passphrase, apply=apply
        )
    except E2eLockedError as exc:
        sys.stdout.write(f"refused: {exc}\n")
        return 1
    verb = "deleted" if apply else "would delete"
    sys.stdout.write(f"{verb} {len(paths)} plaintext blob(s) under /{old_prefix}\n")
    for path in paths:
        sys.stdout.write(f"  {path}\n")
    return 0


def main(argv: list[str]) -> int:  # pragma: no cover - live database entry
    """Parse args and run against the live database."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("old_prefix")
    parser.add_argument("--app", required=True, help="seeded session name")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    client = firebase_client_for(args.app, config=FirebaseConfig.load())
    passphrase = PASSWORD_FILE.read_text(encoding="utf-8").strip()
    return run(client, args.old_prefix, passphrase, apply=args.apply)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
