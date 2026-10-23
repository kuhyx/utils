"""Where the relay keeps its files, and its test seams (contract section 7).

Every default is resolved at call time, so a test that sets an env var after
import still moves the path.
"""

from __future__ import annotations

import os
from pathlib import Path
import time
from typing import Final

DIR_ENV: Final = "LEETCODE_COACH_RELAY_DIR"
PORT_ENV: Final = "LEETCODE_COACH_RELAY_PORT"
RTDB_ENV: Final = "LEETCODE_COACH_RTDB_URL"
CARDS_DRY_RUN_ENV: Final = "LEETCODE_COACH_CARDS_DRY_RUN"
DEFAULT_DIR: Final = Path.home() / ".local" / "share" / "leetcode-coach" / "relay"
HOST: Final = "127.0.0.1"
DEFAULT_PORT: Final = 8777
APP_NAME: Final = "leetcode_coach_relay"
"""The crdt_sync app the relay signs in as (its own token cache)."""


def state_dir() -> Path:
    """``~/.local/share/leetcode-coach/relay`` unless ``$LEETCODE_COACH_RELAY_DIR``."""
    override = os.environ.get(DIR_ENV)
    return Path(override) if override else DEFAULT_DIR


def port() -> int:
    """The loopback port (8777 unless ``$LEETCODE_COACH_RELAY_PORT``)."""
    return int(os.environ.get(PORT_ENV) or DEFAULT_PORT)


def rtdb_url() -> str | None:
    """A database URL that skips Firebase sign-in (the fake RTDB), if set."""
    return os.environ.get(RTDB_ENV) or None


def cards_dry_run() -> bool:
    """Whether step 5 only validates its cards (the live smoke run)."""
    return os.environ.get(CARDS_DRY_RUN_ENV) == "1"


def now_ms() -> int:
    """Wall-clock unix milliseconds."""
    return time.time_ns() // 1_000_000
