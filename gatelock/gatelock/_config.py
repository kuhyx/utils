# Copyright (c) 2026 Krzysztof Rudnicki
"""Declarative configuration and design tokens for :class:`LockWindow`.

Split out of :mod:`gatelock._window` so that the runtime mechanics (grab, VT,
lifecycle) and the *declarative* surface an embedding app actually fills in
can each be read in one piece. :class:`LockConfig` carries no behaviour beyond
resolving its own presets and the design-system scales, and nothing here
imports the window machinery -- the dependency runs one way only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from gatelock import _density
from gatelock._arbiter import RANK_SCREEN_LOCKER
from gatelock._theme import (
    LockPalette,
    LockSpacing,
    LockTypography,
    SpaceStep,
    TypeRole,
)

GrabKind = Literal["none", "local", "global"]
LockMode = Literal["soft", "hard"]


@dataclass(frozen=True)
class GrabPolicy:
    """How the lock takes and keeps the input grab.

    Each field left as ``None`` is derived from :attr:`LockConfig.mode`; an
    explicit value always overrides the preset for that one axis.

    Attributes:
        kind: Input grab strategy. None = derive from mode.
        disable_vt: Disable Ctrl+Alt+Fn VT switching. None = derive from mode.
        retry_ms: Retry interval in ms for a "global" grab that initially
            fails. 0 means "try once, then fall back to a local grab". Left
            unset (None), a "global" grab retries forever every 200ms.
        log_every: Log a warning every N failed retry-forever attempts.
        preempt_weaker_holder: SIGTERM a lower-ranked incumbent that is
            blocking our grab, instead of retrying against it forever. Only
            the *direction* the arbiter's own ranking already sanctions: we
            never signal a holder that outranks us. SIGTERM (not SIGKILL) so
            the holder's own signal handler runs its normal close() path --
            same teardown as a clean dismiss, just triggered externally.
            Defaults to False, and must stay opt-in: for an *enforcement*
            lock (screen_locker), being preempted means the machine unlocks
            with the obligation unmet. Only an app whose own dismissal is
            harmless -- or which genuinely outranks every enforcer -- should
            turn this on, and only after considering who it can now evict.
    """

    kind: GrabKind | None = None
    disable_vt: bool | None = None
    retry_ms: int | None = None
    log_every: int = 25
    preempt_weaker_holder: bool = False


@dataclass(frozen=True)
class LockConfig:
    """Declarative knobs for one :class:`LockWindow` instance.

    ``overrideredirect`` and the grab policy's ``None`` fields are derived
    from ``mode``; an explicit value always overrides the preset for that one
    axis. The visual vocabulary lives in the three :mod:`gatelock._theme`
    records, overridden as a unit.

    Attributes:
        mode: Preset bundling the common combination. "soft" = topmost only,
            typeable, WM-escapable. "hard" = overrideredirect + global grab +
            VT-disable (the production lock for all three apps).
        overrideredirect: Force a WM-unmanaged window. None = derive from mode.
            Note that per-output placement *requires* this: a window manager
            rewrites a managed window's geometry wholesale.
        grab: How the input grab is taken and kept; see :class:`GrabPolicy`.
        app_name: This app's name, used in arbitration logs so a blocked app
            can say who is actually holding the screen.
        rank: Arbitration priority; higher wins. See the ``RANK_*`` constants
            in :mod:`gatelock._arbiter`.
        recovery_tick_ms: Interval of the full re-assertion pass.
        detect_drain_ms: Interval of the cheap "did anything change?" drain.
        palette: Colours; see :class:`gatelock._theme.LockPalette`.
        typography: Font family and type scale;
            see :class:`gatelock._theme.LockTypography`.
        spacing: Spacing scale and focus-ring width;
            see :class:`gatelock._theme.LockSpacing`.
    """

    mode: LockMode = "hard"
    overrideredirect: bool | None = None
    grab: GrabPolicy = field(default_factory=GrabPolicy)
    app_name: str = "gatelock"
    rank: int = RANK_SCREEN_LOCKER
    recovery_tick_ms: int = 1000
    detect_drain_ms: int = 100
    palette: LockPalette = field(default_factory=LockPalette)
    typography: LockTypography = field(default_factory=LockTypography)
    spacing: LockSpacing = field(default_factory=LockSpacing)

    def type_px(self, role: TypeRole = "body") -> int:
        """Return the type-scale size for ``role``, in pixels.

        Compacted on short displays -- see :mod:`gatelock._density`. The scale
        is authored for 1080p; a 768px panel gets 0.8 of it, because a lock
        surface has to fit one screen and cannot scroll its way out of being
        too tall.
        """
        return _density.scale_type(int(getattr(self.typography, role)))

    def space(self, step: SpaceStep = "md") -> int:
        """Return the spacing-scale value for ``step``, in pixels.

        Compacted on short displays, exactly like :meth:`type_px`.
        """
        return _density.scale_space(int(getattr(self.spacing, step)))

    def font(
        self,
        role: TypeRole = "body",
        *,
        bold: bool = False,
        family: str | None = None,
        scale: float = 1.0,
    ) -> tuple[str, int] | tuple[str, int, str]:
        """Return a Tk font tuple for a type-scale role, sized in **pixels**.

        Tk encodes the unit in the *sign* of the size: positive means points,
        negative means pixels. The design-system scale is in pixels, so passing
        e.g. ``type_body`` (16) straight to Tk yields 16 *points* -- about 37%
        larger than intended (measured: linespace 26px vs 19px). Inflating
        every string by a third is enough on its own to push a layout off a
        768px-tall screen, which is exactly what happened to the diet_guard
        meal gate. Always build lock-window fonts through this method.

        Args:
            role: Type-scale role.
            bold: Append Tk's ``"bold"`` weight.
            family: Override the font family. Defaults to the typography's.
            scale: Multiplier for display-only emphasis (e.g. an oversized
                countdown). Kept explicit so outliers are visible rather than
                hidden behind a fresh literal.

        Returns:
            A Tk font tuple with a negative (pixel) size.
        """
        px = max(1, round(self.type_px(role) * scale))
        name = family if family is not None else self.typography.font_family
        return (name, -px, "bold") if bold else (name, -px)

    def focus_kwargs(self) -> dict[str, str | int]:
        """Return widget kwargs that make focus visible on this palette.

        ``highlightcolor`` is the *focused* ring; ``highlightbackground`` is the
        unfocused one. Both are set so the widget shows a subdued edge when
        unfocused and the accent ring when focused -- rather than Tk's default
        black-on-``bg``, which reads as no ring at all.
        """
        return {
            "highlightcolor": self.palette.focus_ring,
            "highlightbackground": self.palette.bg,
            "highlightthickness": self.spacing.focus_thickness,
        }

    def resolved_overrideredirect(self) -> bool:
        """Return the effective overrideredirect setting."""
        if self.overrideredirect is not None:
            return self.overrideredirect
        return self.mode == "hard"

    def resolved_grab(self) -> GrabKind:
        """Return the effective grab strategy."""
        if self.grab.kind is not None:
            return self.grab.kind
        return "global" if self.mode == "hard" else "none"

    def resolved_disable_vt(self) -> bool:
        """Return whether VT switching should be disabled."""
        if self.grab.disable_vt is not None:
            return self.grab.disable_vt
        return self.mode == "hard"
