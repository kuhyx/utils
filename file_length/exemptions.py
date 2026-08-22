"""Predicates deciding whether a file is exempt from the 250-line cap.

Split from :mod:`file_length.config`, which holds the tables these read.
Keeping the rules separate from the data they consult means a new exemption
is a table entry, not a new branch, and the gate and the survey keep sharing
one definition of "exempt".

Re-exported from :mod:`file_length.config`, so existing
``from file_length.config import is_generated`` imports keep working.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from file_length._tables import (
    DATA_TXT_MAX_MEAN_LINE,
    EXCLUDED_DIRS,
    GENERATED_MARKERS,
    GENERATED_PATTERN,
    SESSION_ARTIFACTS_ANYWHERE,
    THIRD_PARTY_REPOS,
    VENDORED_ANYWHERE,
    VENDORED_SUBPATHS,
)

if TYPE_CHECKING:
    from pathlib import Path


def is_generated(path: Path) -> bool:
    """True if the file is tool-generated and must not be split by hand."""
    if GENERATED_PATTERN.search(path.as_posix()):
        return True
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            head = "".join(next(handle, "") for _ in range(5))
    except OSError:
        return False
    return any(marker in head for marker in GENERATED_MARKERS)


def is_data_text(path: Path, lines: int, size: int) -> bool:
    """True for wordlist-style .txt: many lines, very short ones."""
    if path.suffix.lower() != ".txt" or lines <= 0:
        return False
    return (size / lines) < DATA_TXT_MAX_MEAN_LINE


def is_vendored(path: Path) -> bool:
    """True if the path sits under a known vendored subtree or excluded dir.

    Callers must pass an absolute path (see `check.absolutize`). Every rule
    below needs the repo-name context that a repo-relative path has already
    thrown away: '/.claude/skills/' cannot match 'skills/x.md', so a relative
    path would quietly skip the exemption instead of applying it.
    """
    parts = path.parts
    if any(part in EXCLUDED_DIRS for part in parts):
        return True
    posix = path.as_posix()
    if any(marker in posix for marker in VENDORED_ANYWHERE):
        return True
    for repo, subs in VENDORED_SUBPATHS.items():
        for sub in subs:
            if f"/{repo}/{sub}/" in posix:
                return True
    return any(f"/{repo}/" in posix for repo in THIRD_PARTY_REPOS)


def is_session_artifact(path: Path) -> bool:
    """True for a frozen agent-session record (a plan or a session log).

    Kept separate from `is_vendored` so the gate reports why a file is exempt:
    these are kuhy's own files, not third-party code.

    Callers must pass an absolute path (see `check.absolutize`), for the same
    reason `is_vendored` does -- a repo-relative path has already dropped the
    leading directory these markers match on.
    """
    posix = path.as_posix()
    return any(marker in posix for marker in SESSION_ARTIFACTS_ANYWHERE)
