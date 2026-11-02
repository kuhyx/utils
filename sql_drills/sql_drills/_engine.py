"""Docker wrapper around one long-lived pinned ``mysql:8.0.33`` container."""

from __future__ import annotations

from dataclasses import dataclass
import os
import shutil
import subprocess
import time
from typing import TYPE_CHECKING

from sql_drills import _secret

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

IMAGE = "mysql:8.0.33"
CONTAINER = "sql-drills-mysql"
NETWORK = "sql-drills-net"
NETWORK_ALIAS = "db"
READY_TIMEOUT = 45.0
QUERY_TIMEOUT = 30.0
_DOCKER_TIMEOUT = 50.0
# Learner SQL runs as this OS user (nobody): no root shell, no datadir access.
_LEARNER_UID = "65534"
# ``mysql`` reads the root password from this variable, never from argv.
_ROOT_LOGIN_VAR = "MYSQL_PWD"


class EngineError(RuntimeError):
    pass


@dataclass(frozen=True)
class SqlResult:
    returncode: int
    stdout: str
    stderr: str


def _docker(
    *args: str,
    stdin: str | None = None,
    timeout: float = _DOCKER_TIMEOUT,
    env: Mapping[str, str] | None = None,
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
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        msg = f"docker {args[0]} timed out after {timeout:.0f}s"
        raise EngineError(msg) from exc


docker = _docker  # public alias for sibling engine modules


def _root_env() -> dict[str, str]:
    """Environment carrying the root password to ``docker`` (not via argv)."""
    return {**os.environ, _ROOT_LOGIN_VAR: _secret.root_password()}


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
        "-e", "MYSQL_ROOT_PASSWORD",
        *(shared if net.returncode == 0 else []),
        IMAGE,
        env={**os.environ, "MYSQL_ROOT_PASSWORD": _secret.root_password()},
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
    secure_root()


def secure_root() -> None:
    """Make sure root has our password; adopt a legacy passwordless root once.

    A container started before this existed (or restarted from its old
    ``ALLOW_EMPTY_PASSWORD`` config) has an empty root password. Set it live,
    without recreating the container: its tmpfs holds databases we must keep.
    """
    if run_sql("SELECT 1;").returncode == 0:
        return
    password = _secret.root_password()
    alter = "".join(
        f"ALTER USER IF EXISTS 'root'@'{host}' IDENTIFIED BY '{password}'; "
        for host in ("localhost", "%")
    )
    res = exec_query(["exec", "-i", CONTAINER, "mysql", "-uroot"], alter, QUERY_TIMEOUT)
    if res.returncode != 0:
        msg = (
            "MySQL root rejects the stored password and is not passwordless: "
            f"{res.stderr.strip()}; remove {CONTAINER} to start over"
        )
        raise EngineError(msg)


def stop() -> None:
    _docker("rm", "-f", CONTAINER)


def exec_query(
    argv: list[str],
    stdin: str | None,
    timeout: float,
    env: Mapping[str, str] | None = None,
) -> SqlResult:
    """``docker <argv>`` as a query: a timeout becomes a clear EngineError."""
    try:
        res = _docker(*argv, stdin=stdin, timeout=timeout, env=env)
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
    r"""Run ``sql`` through the ``mysql`` client as ``user``.

    ``--binary-mode`` turns every client command (``\!`` shell escape,
    ``source``, ``\.``) into an error for piped input. Only root gets the
    password, and only the learner path drops to an unprivileged OS user.
    """
    root = user == "root"
    argv = ["exec", "-i"]
    argv += ["-e", _ROOT_LOGIN_VAR] if root else ["-u", _LEARNER_UID]
    argv += [CONTAINER, "mysql", f"-u{user}", "--binary-mode"]
    argv += ["--default-character-set=utf8mb4", "-B"]
    if not headers:
        argv.append("-N")
    if database:
        argv.append(database)
    return exec_query(argv, sql, timeout, _root_env() if root else None)
