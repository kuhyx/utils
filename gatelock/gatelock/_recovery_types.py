# Copyright (c) 2026 Krzysztof Rudnicki
"""The value types one recovery tick produces and consumes.

Split from :mod:`gatelock._recovery` for the 250-line cap. Data only -- no
behaviour, and deliberately no import of the loop, so a caller can type
against a report without pulling in the machinery that builds one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from gatelock._config import LockConfig
    from gatelock._detect import OutputChangeDetector
    from gatelock._hooks import LockWindowHooks
    from gatelock._outputs import OutputEnumerator
    from gatelock._surfaces import SurfaceDelta, SurfaceSet


class GrabHeldListener(Protocol):
    """Told whether the grab is really ours (``Claim.grab_held``)."""

    def __call__(self, *, held: bool) -> None:
        """Record the grab state."""


def ignore_grab_held(*, held: bool) -> None:
    """Default :class:`GrabHeldListener`: no arbiter to tell."""
    del held


@dataclass(frozen=True)
class RecoveryReport:
    """What one tick observed and corrected."""

    scan_ok: bool
    source: str
    live_outputs: tuple[str, ...] = ()
    delta: SurfaceDelta | None = None
    corrected: tuple[str, ...] = ()
    grab_reasserted: bool = False
    vt_reasserted: bool = False
    blind: tuple[str, ...] = ()


@dataclass(frozen=True)
class RecoveryCollaborators:
    """The pieces one tick re-asserts over.

    Bundled to keep the loop's constructor at one object instead of a
    growing, unbounded arg list.
    """

    config: LockConfig
    surfaces: SurfaceSet
    enumerator: OutputEnumerator
    detector: OutputChangeDetector
    hooks: LockWindowHooks
    on_grab_held: GrabHeldListener = ignore_grab_held
    """Told each tick whether the grab is really ours (``Claim.grab_held``)."""
