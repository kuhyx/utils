"""Shared configuration for the 250-line file-length cap.

Single source of truth for the cap and its exemptions, imported by both the
pre-commit gate (`check.py`) and the survey. This module is the public
surface: :mod:`file_length._tables` holds the data, and
:mod:`file_length.exemptions` the rules that read it.
"""

from __future__ import annotations

from file_length._tables import (
    CAPPED_EXTENSIONS,
    DATA_TXT_MAX_MEAN_LINE,
    EXCLUDED_DIRS,
    GENERATED_MARKERS,
    GENERATED_PATTERN,
    MAX_LINES,
    SESSION_ARTIFACTS_ANYWHERE,
    THIRD_PARTY_REPOS,
    VENDORED_ANYWHERE,
    VENDORED_SUBPATHS,
)
from file_length.exemptions import (
    is_data_text,
    is_generated,
    is_session_artifact,
    is_vendored,
)

__all__ = [
    "CAPPED_EXTENSIONS",
    "DATA_TXT_MAX_MEAN_LINE",
    "EXCLUDED_DIRS",
    "GENERATED_MARKERS",
    "GENERATED_PATTERN",
    "MAX_LINES",
    "SESSION_ARTIFACTS_ANYWHERE",
    "THIRD_PARTY_REPOS",
    "VENDORED_ANYWHERE",
    "VENDORED_SUBPATHS",
    "is_data_text",
    "is_generated",
    "is_session_artifact",
    "is_vendored",
]
