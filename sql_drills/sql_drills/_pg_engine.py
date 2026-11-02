"""Docker wrapper around one long-lived pinned ``postgres:18.6`` container.

Same model as the MySQL engine, deliberately separate: its own container, data
on tmpfs, no published port and no shared network. Everything goes through
``docker exec`` + ``psql`` over the container's unix socket (``trust`` auth
there; nothing else can reach the server).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from sql_drills import _engine

if TYPE_CHECKING:
    from collections.abc import Callable
    import subprocess

    from sql_drills._engine import SqlResult

IMAGE = "postgres:18.6"
CONTAINER = "sql-drills-postgres"
READY_TIMEOUT = 60.0
QUERY_TIMEOUT = 30.0
# NULL travels as this mark so it stays distinct from an empty string.
NULL_MARK = "\\N"


def container_state() -> str:
    res = _engine.docker("inspect", "-f", "{{.State.Status}}", CONTAINER)
    return res.stdout.strip() if res.returncode == 0 else "missing"


def is_ready() -> bool:
    # TCP, not the socket: the image's init server listens on the socket only,
    # so this is true only for the final server.
    res = _engine.docker("exec", CONTAINER, "pg_isready", "-h127.0.0.1", "-q")
    return res.returncode == 0


def _create() -> subprocess.CompletedProcess[str]:
    return _engine.docker(
        "run", "-d", "--name", CONTAINER,
        "--tmpfs", "/var/lib/postgresql:rw,size=512m,mode=1777",
        "--memory", "1500m",
        "-e", "POSTGRES_HOST_AUTH_METHOD=trust",
        IMAGE,
    )  # fmt: skip


def ensure_running(
    timeout: float = READY_TIMEOUT,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """Create or resume the container if needed, wait (bounded) for PostgreSQL."""
    _engine.start_or_create(CONTAINER, _create)
    _engine.wait_ready(is_ready, "PostgreSQL", timeout, sleep, clock)


def stop() -> None:
    _engine.docker("rm", "-f", CONTAINER)


def run_sql(
    *commands: str,
    database: str = "postgres",
    user: str = "postgres",
    header: bool = False,
    timeout: float = QUERY_TIMEOUT,
) -> SqlResult:
    """Run each command as its own ``psql -c`` (CSV out, NULL as a mark).

    Commands travel as argv, never through a shell. ``ON_ERROR_STOP`` makes any
    failing command a non-zero exit with the server's message on stderr.
    """
    argv = ["exec", "-i", CONTAINER, "psql", "-X", "-q", "--csv"]
    argv += ["-v", "ON_ERROR_STOP=1", "-P", f"null={NULL_MARK}"]
    argv += ["-U", user, "-d", database]
    if not header:
        argv.append("-t")
    for command in commands:
        argv += ["-c", command]
    return _engine.exec_query(argv, None, timeout)
