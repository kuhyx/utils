"""Read-only git subprocess wrapper.

GIT_OPTIONAL_LOCKS=0 stops even read commands from refreshing the index of a
walked repo, so a run never changes anything in kuhy's checkouts.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


class GitError(RuntimeError):
    """git exited non-zero."""


def git(repo: Path, *args: str) -> bytes:
    """Run `git -C repo args...` and return raw stdout, raising GitError on failure."""
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0", "LC_ALL": "C"}
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], env=env, capture_output=True, check=False
    )
    if proc.returncode != 0:
        raise GitError(proc.stderr.decode(errors="replace").strip())
    return proc.stdout
