"""Shared configuration for the markdown-naming convention.

Single source of truth for the four namespaces, the removal marker and the
exemption list, imported by the pre-commit gate (`check.py`) and the staleness
reporter (`stale.py`). This module is the public surface:
:mod:`md_naming._tables` holds the data, :mod:`md_naming.rules` the predicates.
"""

from __future__ import annotations

from md_naming._tables import (
    ALLOWED_PATTERN,
    COMMUNITY_NAMES,
    EXEMPT_SUBPATHS,
    EXTRA_THIRD_PARTY,
    HARNESS_NAMES,
    MARKER,
    STALE_DAYS,
    TODO_PREFIX,
)
from md_naming.rules import (
    contains_marker,
    has_allowed_name,
    is_exempt,
    is_markdown,
    is_todo,
)

__all__ = [
    "ALLOWED_PATTERN",
    "COMMUNITY_NAMES",
    "EXEMPT_SUBPATHS",
    "EXTRA_THIRD_PARTY",
    "HARNESS_NAMES",
    "MARKER",
    "STALE_DAYS",
    "TODO_PREFIX",
    "contains_marker",
    "has_allowed_name",
    "is_exempt",
    "is_markdown",
    "is_todo",
]
