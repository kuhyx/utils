# Copyright (c) 2026 Krzysztof Rudnicki
"""The one wall-clock seam: tests replace :func:`now` instead of sleeping."""

from __future__ import annotations

from datetime import UTC, datetime
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date


def now() -> float:
    """Unix seconds right now."""
    return time.time()


def today() -> date:
    """The local calendar date right now."""
    return datetime.fromtimestamp(now(), tz=UTC).astimezone().date()
