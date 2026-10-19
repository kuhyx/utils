# Copyright (c) 2026 Krzysztof Rudnicki
"""Shared fixtures: the HMAC key file the maturity rows are signed with."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from earned_time.tests._maturity_rows import KEY

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _no_real_switch_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the leisure switch file at a missing path, never the real /etc one."""
    monkeypatch.setattr(
        "earned_time._leisure.LEISURE_FROM_PATH", tmp_path / "no_leisure_from"
    )


@pytest.fixture
def key_file(tmp_path: Path) -> Path:
    """The test HMAC key, written where a test can point ``maturity`` at it."""
    path = tmp_path / "hmac.key"
    path.write_bytes(KEY)
    return path
