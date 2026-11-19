"""A real git checkout in a temp dir, built without kuhy's git config."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

GIT = shutil.which("git") or "git"


def make_checkout(path: Path, origin: str | None) -> Path:
    """Init a repo at ``path`` with remote ``origin`` (none when None)."""
    env = {"PATH": os.environ["PATH"], "HOME": str(path.parent), "GIT_CONFIG_NOSYSTEM": "1"}
    path.mkdir(parents=True)
    subprocess.run([GIT, "init", "-q", str(path)], check=True, env=env)
    if origin is not None:
        subprocess.run([GIT, "-C", str(path), "remote", "add", "origin", origin], check=True, env=env)
    return path
