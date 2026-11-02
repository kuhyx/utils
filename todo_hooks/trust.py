"""Allow-list of done_check hashes that may be executed on this machine."""

from __future__ import annotations

import hashlib
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def check_hash(done_check: str) -> str:
    return hashlib.sha256(done_check.strip().encode()).hexdigest()


def load_trusted(path: Path) -> set[str]:
    """Hashes in `path`: first token per line, ``#`` lines ignored."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return set()
    return {
        row.split()[0].lower()
        for row in text.splitlines()
        if row.strip() and not row.lstrip().startswith("#")
    }


def is_trusted(path: Path, done_check: str) -> bool:
    return check_hash(done_check) in load_trusted(path)


def add_trusted(path: Path, done_check: str, label: str) -> bool:
    """Append the hash plus an audit label; False if it was already listed."""
    digest = check_hash(done_check)
    if digest in load_trusted(path):
        return False
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    prefix = "\n" if existing and not existing.endswith("\n") else ""
    note = " ".join(label.split())
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as handle:
        handle.write(f"{prefix}{digest}  # {note}\n")
    return True
