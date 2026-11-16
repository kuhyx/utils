# Copyright (c) 2026 Krzysztof Rudnicki
"""The settings of one recorded run, as plain values."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

DEFAULT_FPS = 30


@dataclass(frozen=True)
class RunOptions:
    """What the command line asks of `supervise.run`."""

    force: bool = False  # record bot and test runs too (tests only)
    session: str = ""
    audio: str = "default"  # default | lavfi | <pulse source>
    fps: int = DEFAULT_FPS
    max_seconds: float = 0.0  # the test flag: stop the game this long after recording began


@dataclass(frozen=True)
class RecorderOptions:
    """What the recorder needs to start parts of one session."""

    session: str
    feedback: Path
    fps: int
    audio: str
    nice: str
    usable: frozenset[str]
    backend: str = "x11grab"  # gsr or x11grab
