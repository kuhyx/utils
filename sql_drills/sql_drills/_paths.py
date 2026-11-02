"""Shipped fixtures and the generated-drill data dir (resolved per call)."""

from __future__ import annotations

import os
from pathlib import Path

ENV_VAR = "SQL_DRILLS_DATA"
CONFIG_ENV_VAR = "SQL_DRILLS_CONFIG"


def data_dir() -> Path:
    override = os.environ.get(ENV_VAR, "")
    if override:
        return Path(override)
    return Path.home() / ".local" / "share" / "sql_drills"


def builtin_dir() -> Path:
    return Path(__file__).parent / "fixtures"


def generated_dir() -> Path:
    return data_dir() / "drills"


def config_dir() -> Path:
    """Where the engine's secret lives (never in git, never in the data dir)."""
    override = os.environ.get(CONFIG_ENV_VAR, "")
    if override:
        return Path(override)
    return Path.home() / ".config" / "sql_drills"
