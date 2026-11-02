# Copyright (c) 2026 Krzysztof Rudnicki
"""The one wall-clock seam: tests replace :func:`now` instead of sleeping."""

from __future__ import annotations

from datetime import date
import time


def now() -> float:
    """Unix seconds right now."""
    return time.time()


def today() -> date:
    """The local calendar date right now."""
    return date.fromtimestamp(now())  # noqa: DTZ012 (local day by contract)
