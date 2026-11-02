"""The MySQL root password: random, 0600, readable only by this engine.

The container's root used to be passwordless, so anything that reached a shell
in it (a backslash-bang meta-command) owned every database. Now root has this
password; learner SQL runs as a per-run user that never sees it.
"""

from __future__ import annotations

import contextlib
import os
import secrets

from sql_drills import _paths

_FILE = "root_password"


def root_password() -> str:
    """Read the password, creating it on first use.

    The file appears complete or not at all: written to a private temp name,
    then hard-linked into place (which fails if another process won the race).
    """
    path = _paths.config_dir() / _FILE
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(f".{_FILE}.{secrets.token_hex(4)}")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(secrets.token_urlsafe(24) + "\n")
    try:
        with contextlib.suppress(FileExistsError):
            os.link(tmp, path)
    finally:
        tmp.unlink()
    return path.read_text(encoding="utf-8").strip()
