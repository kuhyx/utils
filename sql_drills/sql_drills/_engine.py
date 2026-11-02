"""Docker wrapper around one long-lived pinned ``mysql:8.0.33`` container."""

from __future__ import annotations

from dataclasses import dataclass
import shutil
import subprocess
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

IMAGE = "mysql:8.0.33"
CONTAINER = "sql-drills-mysql"
NETWORK = "sql-drills-net"
NETWORK_ALIAS = "db"
READY_TIMEOUT = 45.0
QUERY_TIMEOUT = 30.0
_DOCKER_TIMEOUT = 50.0


class EngineError(RuntimeError):
    pass


@dataclass(frozen=True)
class SqlResult:
    returncode: int
    stdout: str
    stderr: str


def _docker(
    *args: str, stdin: str | None = None, timeout: float = _DOCKER_TIMEOUT
) -> subprocess.CompletedProcess[str]:
    exe = shutil.which("docker")
    if exe is None:
        msg = "docker binary not found"
        raise EngineError(msg)
    try:
        return subprocess.run(
            [exe, *args],
            input=stdin,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        msg = f"docker {args[0]} timed out after {timeout:.0f}s"
        raise EngineError(msg) from exc


docker = _docker  # public alias for sibling engine modules


def container_state() -> str:
    res = _docker("inspect", "-f", "{{.State.Status}}", CONTAINER)
    return res.stdout.strip() if res.returncode == 0 else "missing"


def is_ready() -> bool:
    res = _docker(
        "exec", CONTAINER, "mysqladmin", "ping", "-h127.0.0.1", "-uroot", "--silent"
    )
    return res.returncode == 0


def _create() -> subprocess.CompletedProcess[str]:
    net = _docker("network", "inspect", NETWORK)
    shared = ["--network", NETWORK, "--network-alias", NETWORK_ALIAS]
    return _docker(
        "run", "-d", "--name", CONTAINER,
        "--tmpfs", "/var/lib/mysql:rw,size=512m",
        "--memory", "1500m",
        "-e", "MYSQL_ALLOW_EMPTY_PASSWORD=yes",
        *(shared if net.returncode == 0 else []),
        IMAGE,
    )  # fmt: skip


def wait_ready(
    ready: Callable[[], bool],
    label: str,
    timeout: float,
    sleep: Callable[[float], None],
    clock: Callable[[], float],
) -> None:
    """Poll ``ready`` until true or ``timeout`` seconds; say how to resume."""
    deadline = clock() + timeout
    while not ready():
        if clock() >= deadline:
            msg = f"{label} not ready after {timeout:.0f}s; rerun to keep waiting"
            raise EngineError(msg)
        sleep(1.0)


def start_or_create(
    container: str, create: Callable[[], subprocess.CompletedProcess[str]]
) -> None:
    """Make ``container`` run: create it if missing, start it if stopped."""
    found = _docker("inspect", "-f", "{{.State.Status}}", container)
    state = found.stdout.strip() if found.returncode == 0 else "missing"
    if state == "running":
        return
    res = create() if state == "missing" else _docker("start", container)
    if res.returncode != 0:
        msg = f"could not start container: {res.stderr.strip()}"
        raise EngineError(msg)


def ensure_running(
    timeout: float = READY_TIMEOUT,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """Create or resume the container if needed, wait (bounded) for MySQL."""
    start_or_create(CONTAINER, _create)
    wait_ready(is_ready, "MySQL", timeout, sleep, clock)


def stop() -> None:
    _docker("rm", "-f", CONTAINER)


def exec_query(argv: list[str], stdin: str | None, timeout: float) -> SqlResult:
    """``docker <argv>`` as a query: a timeout becomes a clear EngineError."""
    try:
        res = _docker(*argv, stdin=stdin, timeout=timeout)
    except EngineError as exc:
        if "timed out" in str(exc):
            msg = f"query timed out after {timeout:.0f}s"
            raise EngineError(msg) from exc
        raise
    return SqlResult(res.returncode, res.stdout, res.stderr)


def run_sql(
    sql: str,
    database: str | None = None,
    user: str = "root",
    *,
    headers: bool = False,
    timeout: float = QUERY_TIMEOUT,
) -> SqlResult:
    argv = ["exec", "-i", CONTAINER, "mysql", f"-u{user}"]
    argv += ["--default-character-set=utf8mb4", "-B"]
    if not headers:
        argv.append("-N")
    if database:
        argv.append(database)
    return exec_query(argv, sql, timeout)
