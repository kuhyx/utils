# Copyright (c) 2026 Krzysztof Rudnicki
"""projects.json: whole-file atomic writes under one flock (single writer)."""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import tempfile
from typing import TYPE_CHECKING

from focus_project._errors import RegistryError
from focus_project._model import Project
from focus_project._paths import data_dir, lock_path, projects_path

if TYPE_CHECKING:
    from collections.abc import Iterator


@contextmanager
def locked() -> Iterator[None]:
    """Hold the exclusive writer lock for a read-modify-write."""
    data_dir().mkdir(parents=True, exist_ok=True)
    with lock_path().open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def read_all() -> list[Project]:
    """Every project; a missing file is empty, a bad one raises."""
    try:
        text = projects_path().read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    try:
        rows = json.loads(text)["projects"]
        if not isinstance(rows, list):
            msg = "'projects' is not a list"
            raise TypeError(msg)  # noqa: TRY301
    except (ValueError, KeyError, TypeError) as exc:
        msg = f"unreadable {projects_path()}: {exc}"
        raise RegistryError(msg) from exc
    return [Project.from_dict(row) for row in rows]


def write_all(projects: list[Project]) -> None:
    """Replace the file atomically: temp file in the same dir, fsync, rename."""
    target = projects_path()
    payload = json.dumps({"projects": [p.to_dict() for p in projects]}, indent=2)
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix="projects.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)  # noqa: PTH105
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
