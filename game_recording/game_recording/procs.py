# Copyright (c) 2026 Krzysztof Rudnicki
"""Helpers for starting the external programs (ffmpeg, gpu-screen-recorder, xdotool, mpv)."""

import shutil
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from typing import IO


def program(name: str) -> str:
    """The full path of an installed program; the bare name when it is not on PATH (the start then fails clearly)."""
    return shutil.which(name) or name


def niced(nice: str, argv: Sequence[str]) -> list[str]:
    """`argv` run under `nice -n <nice>`: when the CPU is contended the game wins, not the recorder."""
    return [program("nice"), "-n", nice, *argv]


def spawn(
    argv: Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
    log: IO[bytes] | None = None,
    detach: bool = False,
) -> subprocess.Popen[bytes]:
    """Starts a child that outlives this call; `log` takes its output, `detach` gives it its own session."""
    return subprocess.Popen(
        list(argv), env=None if env is None else dict(env), stdout=log, stderr=log, start_new_session=detach
    )
