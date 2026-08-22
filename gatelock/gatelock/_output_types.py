"""The value types describing a display output and a scan of them.

Split from :mod:`gatelock._outputs` so the two backends
(:mod:`gatelock._randr`, :mod:`gatelock._xrandr`) can import the types without
importing the enumerator that uses them -- which is what would otherwise make
the dependency circular.

Re-exported from :mod:`gatelock._outputs`, so existing imports keep working.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

OutputSource = Literal["randr", "xrandr", "tk", "none"]


@dataclass(frozen=True)
class OutputRect:
    """A rectangle in root-window coordinates."""

    x: int
    y: int
    width: int
    height: int

    def geometry(self) -> str:
        """Return the Tk geometry string for this rectangle."""
        return f"{self.width}x{self.height}+{self.x}+{self.y}"


@dataclass(frozen=True)
class Output:
    """A single X output and whether anything can actually be seen on it."""

    name: str
    connected: bool
    rect: OutputRect | None
    primary: bool = False

    @property
    def live(self) -> bool:
        """Whether this output is connected *and* has a mode."""
        return self.connected and self.rect is not None


@dataclass(frozen=True)
class OutputScan:
    """The result of one enumeration attempt.

    ``ok`` records whether enumeration itself succeeded, which is a different
    question from whether any output is live. Callers must not conflate them:
    a failed scan means "no information, change nothing", while a successful
    scan with zero live outputs means "the screens really are dark".
    """

    outputs: tuple[Output, ...]
    source: OutputSource
    ok: bool

    @property
    def live(self) -> tuple[Output, ...]:
        """The subset of outputs that are connected and have a mode."""
        return tuple(output for output in self.outputs if output.live)
