# Copyright (c) 2026 Krzysztof Rudnicki
"""Which GitHub repo a local checkout is, read from its ``origin`` remote.

A folder name says nothing about the owner: ``~/src/cleanup-plate`` is
``Sepci0/cleanup-plate`` and ``~/src/todo`` is ``kuhyx/todo-app``. Guessing
``<owner>/<folder>`` filed tasks and error tickets under repos that do not exist, so the guess is
only the fallback for a folder with no checkout or no GitHub origin.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

GIT_TIMEOUT = 5.0
# https://[user@]github.com/o/n[.git], ssh://git@github.com[:port]/o/n[.git]
# and git@github.com:o/n[.git]. Other hosts (a local mirror, a gitea) are not
# the GitHub slug the board works with, so they fall back to the guess.
_GITHUB = re.compile(
    r"^(?:https?://(?:[^@/]+@)?github\.com/|ssh://git@github\.com(?::\d+)?/"
    r"|git@github\.com:)(?P<slug>[^/\s]+/[^/\s]+?)(?:\.git)?/?$"
)


def slug_from_url(url: str) -> str | None:
    """Return ``owner/name`` of a GitHub remote URL, or None for any other URL."""
    match = _GITHUB.match(url.strip())
    return match["slug"] if match else None


def origin_slug(checkout: Path) -> str | None:
    """Return the GitHub ``owner/name`` of ``checkout``'s origin, or None.

    None when ``checkout`` is not a git checkout (a ``.git`` dir, or file for a
    worktree), has no ``origin``, git is missing or hangs, or origin is not
    GitHub. Checking ``.git`` first keeps git from walking up to a parent repo.
    """
    git = shutil.which("git")
    if git is None or not (checkout / ".git").exists():
        return None
    try:
        out = subprocess.run(
            [git, "-C", str(checkout), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=False,
            timeout=GIT_TIMEOUT,
        )
    except OSError, subprocess.SubprocessError:
        return None
    return None if out.returncode else slug_from_url(out.stdout)


def repo_slug(src_root: Path, folder: str, owner: str) -> str:
    """Return the slug of ``src_root/folder``'s origin, else ``owner/folder``."""
    return origin_slug(src_root / folder) or f"{owner}/{folder}"
