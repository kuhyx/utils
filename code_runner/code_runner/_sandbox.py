from __future__ import annotations

from dataclasses import dataclass
import functools
import math
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
from typing import IO

from code_runner._model import MAX_CAPTURE, Limits, RunnerError

WORK = "/work"
PRLIMIT = "/usr/bin/prlimit"
_ROOT_LINKS = ("bin", "sbin", "lib", "lib64")


@dataclass(frozen=True)
class BoxResult:
    returncode: int
    timed_out: bool
    stdout: str
    stderr: str
    elapsed_ms: float


def _root_links() -> list[str]:
    args: list[str] = []
    for name in _ROOT_LINKS:
        path = Path("/") / name
        if path.is_symlink():
            args += ["--symlink", str(path.readlink()), str(path)]
        elif path.is_dir():
            args += ["--ro-bind", str(path), str(path)]
    return args


def _base_argv() -> list[str]:
    return [
        "bwrap",
        "--unshare-all",  # no --share-net: no network at all, loopback included
        "--die-with-parent",
        "--new-session",
        "--clearenv",
        "--ro-bind",
        "/usr",
        "/usr",
        *_root_links(),
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
    ]


def bwrap_argv(
    command: list[str],
    scratch: Path,
    limits: Limits,
    memory_bytes: int,
    ro_binds: tuple[str, ...] = (),
) -> list[str]:
    argv = _base_argv()
    for bind in ro_binds:
        argv += ["--ro-bind", bind, bind]
    argv += ["--bind", str(scratch), WORK, "--remount-ro", "/", "--chdir", WORK]
    for name, value in (
        ("HOME", WORK),
        ("PATH", "/usr/bin"),
        ("LANG", "C.UTF-8"),
        ("PYTHONIOENCODING", "utf-8"),
    ):
        argv += ["--setenv", name, value]
    cpu = math.ceil(limits.timeout_s) + 1
    return [
        *argv,
        "--",
        PRLIMIT,
        f"--as={memory_bytes}",
        f"--nproc={limits.nproc}",
        f"--fsize={limits.fsize_bytes}",
        f"--nofile={limits.nofile}",
        f"--cpu={cpu}",
        "--core=0",
        "--",
        *command,
    ]


@functools.cache
def check_sandbox() -> None:
    if not Path(PRLIMIT).is_file():
        msg = f"{PRLIMIT} is missing (util-linux)"
        raise RunnerError(msg)
    try:
        probe = subprocess.run(
            [*_base_argv(), "/usr/bin/true"],
            capture_output=True,
            check=False,
            timeout=20,
        )
    except OSError as exc:
        msg = f"bubblewrap (bwrap) cannot start: {exc}"
        raise RunnerError(msg) from exc
    if probe.returncode != 0:
        detail = probe.stderr.decode(errors="replace").strip()
        msg = f"bubblewrap cannot create the sandbox: {detail}"
        raise RunnerError(msg)


def _read(handle: IO[bytes]) -> str:
    handle.seek(0)
    return handle.read(MAX_CAPTURE).decode("utf-8", errors="replace")


def execute(
    command: list[str],
    scratch: Path,
    limits: Limits,
    memory_bytes: int,
    ro_binds: tuple[str, ...] = (),
) -> BoxResult:
    check_sandbox()
    argv = bwrap_argv(command, scratch, limits, memory_bytes, ro_binds)
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        started = time.monotonic()
        with subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=err,
            env={"PATH": "/usr/bin:/bin"},
            start_new_session=True,
        ) as proc:
            timed_out = False
            try:
                proc.wait(timeout=limits.timeout_s)
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(proc.pid, signal.SIGKILL)
        elapsed = (time.monotonic() - started) * 1000
        return BoxResult(proc.returncode, timed_out, _read(out), _read(err), elapsed)
