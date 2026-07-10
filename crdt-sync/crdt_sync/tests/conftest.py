"""Shared pytest fixtures for crdt_sync's test suite."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from crdt_sync import Hlc

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.fixture
def make_hlc() -> Callable[..., Hlc]:
    """Return a factory for deterministic Hlc values."""

    def _make(wall_time_ms: int, counter: int = 0, node_id: str = "node-a") -> Hlc:
        return Hlc(wall_time_ms=wall_time_ms, counter=counter, node_id=node_id)

    return _make
