# Copyright (c) 2026 Krzysztof Rudnicki
"""Errors raised by the registry."""

from __future__ import annotations


class RegistryError(ValueError):
    """projects.json is unreadable, malformed or self-contradictory."""
