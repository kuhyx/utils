# Copyright (c) 2026 Krzysztof Rudnicki
"""Where the data lives, resolved on every call so tests can redirect it."""

from __future__ import annotations

import os
from pathlib import Path

ENV_VAR = "FOCUS_PROJECT_DATA"


def data_dir() -> Path:
    """``$FOCUS_PROJECT_DATA`` or ``~/.local/share/focus_project``."""
    override = os.environ.get(ENV_VAR)
    if override:
        return Path(override)
    return Path.home() / ".local" / "share" / "focus_project"


def projects_path() -> Path:
    """The registry file; this package is its only writer."""
    return data_dir() / "projects.json"


def activity_path() -> Path:
    """The append-only activity log."""
    return data_dir() / "activity.jsonl"


def lock_path() -> Path:
    """The registry's writer lock."""
    return data_dir() / "projects.lock"
