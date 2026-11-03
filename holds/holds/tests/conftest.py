# Copyright (c) 2026 Krzysztof Rudnicki
"""Point the hold file at ``tmp_path`` for every test, so none can touch live state."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def data_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Redirect the data file; the path is resolved per call, so this is enough."""
    path = tmp_path / "state" / "holds.json"
    monkeypatch.setenv("HOLDS_DATA", str(path))
    return path
