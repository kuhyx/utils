# Copyright (c) 2026 Krzysztof Rudnicki
"""Declared time-boxed holds: while one is active every gate stands down.

Stdlib only; gates import it from the system python. Contract v1.
"""

from __future__ import annotations

from holds._api import active, add, covers, next_change, remove
from holds._model import Hold, HoldsError

__all__ = ["Hold", "HoldsError", "active", "add", "covers", "next_change", "remove"]
