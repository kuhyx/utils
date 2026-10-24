"""The headless chromium unit: argv, systemd-run wrapper, size parsing."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from pathlib import Path

from flutter_web_drive.errors import EXIT_USAGE, DriveError

# The real binary: /usr/local/bin/chromium is a hosts-installer wrapper.
CHROMIUM = "/usr/bin/chromium"

Runner = Callable[[list[str]], int]


def run(cmd: list[str]) -> int:
    """Run a short command quietly and return its exit code."""
    return subprocess.run(cmd, check=False, capture_output=True).returncode


def parse_size(size: str) -> tuple[int, int]:
    """``1400x1000`` -> (1400, 1000)."""
    m = re.fullmatch(r"(\d+)x(\d+)", size)
    if not m:
        raise DriveError(
            "start", f"--size must look like 1400x1000, got {size!r}", EXIT_USAGE
        )
    return int(m[1]), int(m[2])


def chromium_argv(
    url: str, profile: Path, cdp_port: int, size: tuple[int, int]
) -> list[str]:
    """Headless chromium with CDP on loopback and a persistent profile.

    ``--disable-extensions`` keeps the Claude extension (loaded via
    chromium-flags.conf) out of this CDP session; ``--password-store=basic``
    stops chromium asking the desktop keyring, which could prompt on :0.
    """
    width, height = size
    return [
        CHROMIUM,
        "--headless=new",
        f"--remote-debugging-port={cdp_port}",
        "--remote-debugging-address=127.0.0.1",
        f"--user-data-dir={profile}",
        "--disable-extensions",
        "--no-first-run",
        "--no-default-browser-check",
        "--password-store=basic",
        "--mute-audio",
        "--hide-scrollbars",
        "--enable-unsafe-swiftshader",
        f"--window-size={width},{height}",
        url,
    ]


def unit_argv(unit: str, argv: list[str]) -> list[str]:
    """``systemd-run --user`` so the browser outlives the calling shell.

    DISPLAY/WAYLAND_DISPLAY are unset in the unit: even a mis-flagged
    chromium then has no live display to open a window on.
    """
    return [
        "systemd-run",
        "--user",
        f"--unit={unit}",
        "--collect",
        "--quiet",
        "-p",
        "UnsetEnvironment=DISPLAY WAYLAND_DISPLAY",
        *argv,
    ]


def unit_active(unit: str, runner: Runner) -> bool:
    """Is the systemd user unit running?"""
    return runner(["systemctl", "--user", "is-active", "--quiet", unit]) == 0
