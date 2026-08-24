"""Predicates deciding whether a markdown file is subject to the convention.

The rule half: :mod:`md_naming._tables` holds the data these read, and
:mod:`md_naming.config` re-exports both as the public surface.

Every predicate takes a full path. Matching a repo-relative path against a
full-path rule silently drops the repo-name context -- the same bug
:func:`md_naming.check.absolutize` exists to prevent.
"""

from __future__ import annotations

from pathlib import Path

from file_length._tables import (
    EXCLUDED_DIRS,
    GENERATED_PATTERN,
    THIRD_PARTY_REPOS,
    VENDORED_ANYWHERE,
)
from md_naming._tables import (
    ALLOWED_PATTERN,
    COMMUNITY_NAMES,
    EXEMPT_SUBPATHS,
    EXTRA_THIRD_PARTY,
    HARNESS_NAMES,
    MARKER,
    TODO_PREFIX,
)

#: Trailing separator included so "/build/" cannot match "/buildings/".
_EXCLUDED_FRAGMENTS = tuple(f"/{name}/" for name in EXCLUDED_DIRS)


def is_markdown(path: Path) -> bool:
    """True if `path` is a markdown file by extension."""
    return path.suffix.lower() in {".md", ".markdown"}


def in_excluded_dir(path: Path) -> bool:
    """True if `path` sits under a dependency, build-output or cache dir."""
    return any(fragment in path.as_posix() for fragment in _EXCLUDED_FRAGMENTS)


def is_third_party(path: Path) -> bool:
    """True if `path` belongs to a clone of someone else's repo.

    Matches on the directory name directly under the home root rather than
    anywhere in the path, so a repo of kuhy's that merely *contains* a
    directory sharing a third-party name is not exempted wholesale.
    """
    parts = path.as_posix().split("/")
    repos = THIRD_PARTY_REPOS | EXTRA_THIRD_PARTY
    return any(part in repos for part in parts)


def is_vendored(path: Path) -> bool:
    """True if `path` is inside a vendored skill bundle or agent tree."""
    posix = path.as_posix()
    return any(fragment in posix for fragment in VENDORED_ANYWHERE)


def is_exempt_subpath(path: Path) -> bool:
    """True if `path` is under a tree whose markdown is externally named."""
    return any(fragment in path.as_posix() for fragment in EXEMPT_SUBPATHS)


def is_reserved_name(path: Path) -> bool:
    """True if the basename is owned by external tooling."""
    return path.name in HARNESS_NAMES or path.name in COMMUNITY_NAMES


def is_generated(path: Path) -> bool:
    """True if `path` matches the shared generated-file pattern."""
    return bool(GENERATED_PATTERN.search(path.as_posix()))


def is_exempt(path: Path) -> bool:
    """True if the naming rule does not apply to `path` at all."""
    return (
        in_excluded_dir(path)
        or is_third_party(path)
        or is_vendored(path)
        or is_exempt_subpath(path)
        or is_reserved_name(path)
        or is_generated(path)
    )


def has_allowed_name(path: Path) -> bool:
    """True if the basename matches one of the four namespaces."""
    return bool(ALLOWED_PATTERN.match(path.name))


def is_todo(path: Path) -> bool:
    """True if `path` is a task file by name."""
    return path.name.startswith(TODO_PREFIX) and is_markdown(path)


def contains_marker(path: Path) -> bool:
    """True if `path` contains the removal marker.

    Unreadable and binary files answer False rather than raising: a file the
    gate cannot read is reported by the naming rule, not crashed on here.
    """
    try:
        return MARKER in path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
