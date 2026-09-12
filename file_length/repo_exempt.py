"""Repo-local exemptions from the 250-line cap: a `.file-length-exempt` file.

The shared tables in :mod:`file_length._tables` hold exemptions that are true
everywhere (generated, vendored, wordlists). A fork of a third-party project
can also carry data that is code only by extension -- TachiyomiSY's
``exh/eh/tags/*.kt`` are 6000-line string tables that upstream regenerates --
and that knowledge belongs next to the data, in the repo, not in a shared
list every other repo loads.

Format, one entry per line, glob relative to the repo root::

    app/src/main/java/exh/eh/tags/*.kt   # tag data tables mirrored from upstream

The reason is mandatory. An entry without one is a suppression, so the gate
fails closed on it (exit 2) instead of honouring it silently.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path, PurePosixPath

#: Basename of the per-repo exemption list, looked up in the gate's cwd.
EXEMPT_FILE = ".file-length-exempt"


class ExemptFileError(ValueError):
    """`.file-length-exempt` is malformed; the gate must not guess."""


@dataclass(frozen=True)
class Exemption:
    """One glob plus the human reason it is exempt."""

    pattern: str
    reason: str


def parse(text: str) -> list[Exemption]:
    """Parse the file body; every non-comment entry must carry a reason."""
    entries: list[Exemption] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        pattern, sep, reason = line.partition("#")
        pattern, reason = pattern.strip(), reason.strip()
        if not sep or not reason or not pattern:
            msg = f"{EXEMPT_FILE}:{number}: every entry is '<glob>  # <reason>'"
            raise ExemptFileError(msg)
        entries.append(Exemption(pattern, reason))
    return entries


@cache
def load(root: Path) -> tuple[Exemption, ...]:
    """The exemptions for the repo at `root`, empty when it has no file."""
    path = root / EXEMPT_FILE
    if not path.is_file():
        return ()
    return tuple(parse(path.read_text(encoding="utf-8")))


def repo_exempt_reason(path: Path, root: Path) -> str | None:
    """The repo-local reason `path` is exempt, or None if no entry matches.

    `path` must be absolute (see `check.absolutize`); anything outside `root`
    is not the repo's to exempt and gets None.
    """
    entries = load(root)
    if not entries:
        return None
    try:
        relative = PurePosixPath(path.relative_to(root).as_posix())
    except ValueError:
        return None
    for entry in entries:
        if relative.full_match(entry.pattern):
            return f"repo exemption: {entry.reason}"
    return None
