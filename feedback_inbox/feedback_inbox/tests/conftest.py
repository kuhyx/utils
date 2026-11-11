# Copyright (c) 2026 Krzysztof Rudnicki
"""Redirect the one path resolver, so no test can touch real user state.

Every writer resolves its paths through ``feedback_inbox._paths.resolve_paths``;
redirecting that one function moves all of them (kuhy's real ``~/data``,
token file, lock and systemd unit dir included).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from feedback_inbox._paths import Paths

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Paths:
    """Point every default path at ``tmp_path`` before any test runs."""
    redirected = Paths.under(tmp_path / "home")

    def _resolve(given: Paths | None = None) -> Paths:
        return given if given is not None else redirected

    monkeypatch.setattr("feedback_inbox._cli.resolve_paths", _resolve)
    redirected.data_root.mkdir(parents=True)
    return redirected
