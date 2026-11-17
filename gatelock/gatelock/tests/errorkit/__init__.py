# Copyright (c) 2026 Krzysztof Rudnicki
"""Shared pieces of the error reporter tests: a settable clock, spool lines."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


class Clock:
    """A settable wall + monotonic clock."""

    def __init__(self) -> None:
        self.t = 1_800_000_000.0

    def __call__(self) -> float:
        return self.t


def spool_lines(tmp_path: Path, app: str = "leetcode-guard") -> list[dict[str, object]]:
    path = tmp_path / f"{app}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


def _boom() -> None:
    msg = "bad 12"
    raise ValueError(msg)


def raised() -> BaseException:
    """A ValueError carrying a real traceback."""
    try:
        _boom()
    except ValueError as e:
        return e
    raise AssertionError
