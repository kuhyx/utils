# Copyright (c) 2026 Krzysztof Rudnicki
"""Read-only E2E done check: list plaintext leaves in an RTDB JSON dump.

Feed it ``firebase database:get /<root>`` on stdin::

    firebase database:get /todo-sync | python3 -m tool.e2e_audit todo-sync

Exit 0 when every leaf is sealed (or is the clear Argon2id header or a keyed
revision), 1 when any leaf is plaintext. A plain ``grep '"title"'`` misses
plaintext because RTDB serves each blob as an escaped JSON string; this
decodes the tree instead.
"""

from __future__ import annotations

import json
import re
import sys

from crdt_sync import is_e2e_envelope

_HEX64 = re.compile(r"[0-9a-f]{64}")


def _decode_key(key: str) -> str:
    return re.sub(r"~([0-9A-F]{2})", lambda m: chr(int(m.group(1), 16)), key)


def _is_clear_leaf(value: str) -> bool:
    # Envelopes and the Argon2id header both carry an integer "v"; keyed
    # revisions are 64 hex chars; a bare E2eCipher blob is base64, not JSON.
    if is_e2e_envelope(value) or _HEX64.fullmatch(value):
        return True
    return not value.lstrip().startswith(("{", "["))


def plaintext_paths(tree: object, prefix: str = "") -> list[str]:
    """Return the decoded paths of every plaintext leaf under ``tree``."""
    found: list[str] = []
    if isinstance(tree, dict):
        for key, value in tree.items():
            path = f"{prefix}/{_decode_key(key)}" if prefix else _decode_key(key)
            found.extend(plaintext_paths(value, path))
    elif isinstance(tree, str):
        if not _is_clear_leaf(tree):
            found.append(prefix)
    elif tree is not None:
        found.append(prefix)
    return found


def main(argv: list[str]) -> int:
    """Audit the dump on stdin; ``argv[0]`` names the root for the report."""
    root = argv[0] if argv else ""
    paths = plaintext_paths(json.load(sys.stdin), root)
    sys.stdout.write(f"plaintext leaves under /{root}: {len(paths)}\n")
    for path in paths:
        sys.stdout.write(f"  {path}\n")
    return 1 if paths else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
