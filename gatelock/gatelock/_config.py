"""Declarative configuration and design tokens for :class:`LockWindow`.

Split out of :mod:`gatelock._window` so that the runtime mechanics (grab, VT,
lifecycle) and the *declarative* surface an embedding app actually fills in
can each be read in one piece. :class:`LockConfig` carries no behaviour beyond
resolving its own presets and the design-system scales, and nothing here
imports the window machinery -- the dependency runs one way only.

Imported from :mod:`gatelock._window` as well, so ``from gatelock._window
import LockConfig`` keeps working for the modules and tests that already do.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from gatelock import _density
from gatelock._arbiter import RANK_SCREEN_LOCKER

GrabKind = Literal["none", "local", "global"]
LockMode = Literal["soft", "hard"]
TypeRole = Literal["display", "title", "subtitle", "body", "label", "caption"]
SpaceStep = Literal["xs", "sm", "md", "lg", "xl", "xxl"]


@dataclass(frozen=True)
class LockConfig:
    """Declarative knobs for one :class:`LockWindow` instance.

    Each field left as ``None`` is derived from ``mode``; an explicit value
    always overrides the preset for that one axis.

    Attributes:
        mode: Preset bundling the common combination. "soft" = topmost only,
            typeable, WM-escapable. "hard" = overrideredirect + global grab +
            VT-disable (the production lock for all three apps).
        overrideredirect: Force a WM-unmanaged window. None = derive from mode.
            Note that per-output placement *requires* this: a window manager
            rewrites a managed window's geometry wholesale.
        grab: Input grab strategy. None = derive from mode.
        disable_vt: Disable Ctrl+Alt+Fn VT switching. None = derive from mode.
        grab_retry_ms: Retry interval in ms for a "global" grab that initially
            fails. 0 means "try once, then fall back to a local grab". Left
            unset (None), a "global" grab retries forever every 200ms.
        grab_log_every: Log a warning every N failed retry-forever attempts.
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
        app_name: This app's name, used in arbitration logs so a blocked app
            can say who is actually holding the screen.
        rank: Arbitration priority; higher wins. See the ``RANK_*`` constants
            in :mod:`gatelock._arbiter`.
        recovery_tick_ms: Interval of the full re-assertion pass.
        detect_drain_ms: Interval of the cheap "did anything change?" drain.
        bg: Background color for the lock surfaces.
        fg: Primary (near-white) text color.
        muted: Secondary/caption text color.
        field_bg: Background for "raised" surfaces (entry/spinbox fields,
            input wells) -- one step lighter than ``bg``.
        accent: The shared brand accent (buttons, primary actions).
        success: Positive/on-track status color.
        warning: Caution/pending status color.
        danger: Negative/error status color.
        on_fill: Text/icon color for anything drawn on top of a filled
            accent/success/warning/danger surface (e.g. a button's label) --
            NOT ``fg``. All four fills sit in the same mid-light band, so
            near-white text under-contrasts on every one of them; callers
            must pick ``fg`` vs. ``on_fill`` based on the widget's own
            background, never hardcode one for all buttons.
        font_family: Default font family for lock-window widgets.
        focus_ring: Color of the *focused* widget's highlight ring. Defaults to
            ``accent``, because Tk's own default is black -- invisible against
            ``bg``. Pass to ``highlightcolor``; note ``highlightbackground`` is
            the *unfocused* ring, so setting that one inverts the affordance.
        focus_thickness: Ring width in px. Never set 0 on a focusable widget.
        type_display, type_title, type_subtitle, type_body, type_label,
            type_caption: The type scale, in **pixels**. Do not pass these to
            Tk directly -- use :meth:`font`, which applies the sign convention.
        space_xs, space_sm, space_md, space_lg, space_xl, space_xxl: The 4px
            spacing scale, in pixels. Use for ``padx``/``pady``/``ipadx``.

    All color/font defaults come from the ``unified-design-system`` docs
    (``~/utils/unified-design-system/tokens.md``) -- the same palette used by
    every one of kuhy's apps, Flutter and web included.
    """

    mode: LockMode = "hard"
    overrideredirect: bool | None = None
    grab: GrabKind | None = None
    disable_vt: bool | None = None
    grab_retry_ms: int | None = None
    grab_log_every: int = 25
    preempt_weaker_holder: bool = False
    app_name: str = "gatelock"
    rank: int = RANK_SCREEN_LOCKER
    recovery_tick_ms: int = 1000
    detect_drain_ms: int = 100
    bg: str = "#211D1B"
    fg: str = "#ECEAE9"
    muted: str = "#AAA09A"
    field_bg: str = "#2B2624"
    accent: str = "#B8862E"
    success: str = "#8A9A3C"
    warning: str = "#E0A63C"
    danger: str = "#E2585F"
    on_fill: str = "#211D1B"
    font_family: str = "Arial"
    focus_ring: str = "#B8862E"
    focus_thickness: int = 2
    # Type scale in PIXELS (unified-design-system tokens.md). Convert via
    # font(); a raw positive value handed to Tk means *points*, ~37% bigger.
    type_display: int = 32
    type_title: int = 24
    type_subtitle: int = 20
    type_body: int = 16
    type_label: int = 14
    type_caption: int = 12
    # 4px spacing scale, in pixels.
    space_xs: int = 4
    space_sm: int = 8
    space_md: int = 16
    space_lg: int = 24
    space_xl: int = 32
    space_xxl: int = 48

    def type_px(self, role: TypeRole = "body") -> int:
        """Return the type-scale size for ``role``, in pixels.

        Compacted on short displays -- see :mod:`gatelock._density`. The scale
        is authored for 1080p; a 768px panel gets 0.8 of it, because a lock
        surface has to fit one screen and cannot scroll its way out of being
        too tall.
        """
        return _density.scale_type(int(getattr(self, f"type_{role}")))

    def space(self, step: SpaceStep = "md") -> int:
        """Return the spacing-scale value for ``step``, in pixels.

        Compacted on short displays, exactly like :meth:`type_px`.
        """
        return _density.scale_space(int(getattr(self, f"space_{step}")))

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
            family: Override the font family. Defaults to ``font_family``.
            scale: Multiplier for display-only emphasis (e.g. an oversized
                countdown). Kept explicit so outliers are visible rather than
                hidden behind a fresh literal.

        Returns:
            A Tk font tuple with a negative (pixel) size.
        """
        px = max(1, round(self.type_px(role) * scale))
        name = family if family is not None else self.font_family
        return (name, -px, "bold") if bold else (name, -px)

    def focus_kwargs(self) -> dict[str, str | int]:
        """Return widget kwargs that make focus visible on this palette.

        ``highlightcolor`` is the *focused* ring; ``highlightbackground`` is the
        unfocused one. Both are set so the widget shows a subdued edge when
        unfocused and the accent ring when focused -- rather than Tk's default
        black-on-``bg``, which reads as no ring at all.
        """
        return {
            "highlightcolor": self.focus_ring,
            "highlightbackground": self.bg,
            "highlightthickness": self.focus_thickness,
        }

    def resolved_overrideredirect(self) -> bool:
        """Return the effective overrideredirect setting."""
        if self.overrideredirect is not None:
            return self.overrideredirect
        return self.mode == "hard"

    def resolved_grab(self) -> GrabKind:
        """Return the effective grab strategy."""
        if self.grab is not None:
            return self.grab
        return "global" if self.mode == "hard" else "none"

    def resolved_disable_vt(self) -> bool:
        """Return whether VT switching should be disabled."""
        if self.disable_vt is not None:
            return self.disable_vt
        return self.mode == "hard"
