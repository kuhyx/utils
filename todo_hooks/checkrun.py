"""Run a done_check with a hard timeout, in its own process group."""

from __future__ import annotations

from dataclasses import dataclass
import os
import signal
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

CHECK_TIMEOUT = 55.0


@dataclass(frozen=True)
class CheckResult:
    """Exit code, or None on timeout or failure to start."""

    code: int | None
    timed_out: bool

    @property
    def passed(self) -> bool:
        return self.code == 0

    def describe(self) -> str:
        if self.timed_out:
            return f"timed out after {CHECK_TIMEOUT:g}s"
        return "could not start" if self.code is None else f"exit {self.code}"


def run_check(
    command: str,
    cwd: Path,
    *,
    timeout: float = CHECK_TIMEOUT,
    wrapper: Path | None = None,
) -> CheckResult:
    """``bash -c command`` from `cwd` without GIT_* env; kill the group on timeout."""
    argv = [str(wrapper)] if wrapper else []
    argv += ["bash", "-c", command]
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    try:
        proc = subprocess.Popen(
            argv,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return CheckResult(None, timed_out=False)
    try:
        return CheckResult(proc.wait(timeout=timeout), timed_out=False)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
        return CheckResult(None, timed_out=True)
