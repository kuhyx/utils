from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# "any": list order is free; "deep": the order inside its items is free too.
Order = Literal["exact", "any", "deep"]
MAX_CAPTURE = 64 * 1024


class RunnerError(Exception):
    pass


@dataclass(frozen=True)
class Example:
    n: int
    args: dict[str, object]
    expected: object
    order: Order = "exact"


@dataclass(frozen=True)
class CaseResult:
    n: int
    input: dict[str, object]
    expected: object
    actual: object
    ok: bool
    stdout: str = ""
    error: str | None = None
    ms: float = 0.0


@dataclass(frozen=True)
class Limits:
    timeout_s: float = 2.0
    nproc: int = 64
    fsize_bytes: int = 1024 * 1024
    nofile: int = 256
