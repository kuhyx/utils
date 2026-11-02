"""The canonical structural-token table: spacing, radius, type, shadow, motion.

Colour is `palette_map.py`; this is its twin for everything that is not a
colour. Pure data -- parsing and comparison live in `structural_check.py`.

A canonical key is `<kind>.<name>` (`space.sm`, `duration.fast`) and is also
the key the prose freezes (`DOCS-tokens.md`, `DOCS-motion.md`) are parsed
into, so the md stack needs no column of its own. A `None` name means the
token is intentionally absent from that stack and `why` must say so: an
honest `n/a` with a reason, never a fabricated constant.
"""

from __future__ import annotations

from dataclasses import dataclass

STACKS = ("css", "dart", "tk")


@dataclass(frozen=True)
class Token:
    """One canonical structural token and its name in each code stack."""

    canonical: str
    css: str | None
    dart: str | None
    tk: str | None
    why: str = ""

    def __post_init__(self) -> None:
        """Refuse an absence that carries no recorded reason."""
        if None in (self.css, self.dart, self.tk) and not self.why:
            msg = f"{self.canonical}: a stack is n/a but `why` is empty"
            raise ValueError(msg)


_TK_NO_RADIUS = "Tk has no corner-radius primitive: widgets are square."
_TK_NO_MOTION = "Tkinter has no animation framework; a duration would be dead."
_NO_SHADOW = (
    "Dark-first Flutter/Tk surfaces take no shadow (elevation is a fill step); "
    "only web light surfaces opt in."
)
_STEPS = ("xs", "sm", "md", "lg", "xl", "xxl")
_TYPE = ("display", "title", "subtitle", "body", "label", "caption")

TOKENS: tuple[Token, ...] = (
    *(
        Token(f"space.{s}", f"--space-{i}", f"AppSpacing.{s}", f"LockSpacing.{s}")
        for i, s in enumerate(_STEPS, 1)
    ),
    *(
        Token(f"radius.{s}", f"--radius-{s}", f"AppRadius.{s}", None, _TK_NO_RADIUS)
        for s in ("sm", "md", "lg")
    ),
    *(
        Token(f"text.{t}", f"--text-{t}", f"AppTextSize.{t}", f"LockTypography.{t}")
        for t in _TYPE
    ),
    *(Token(f"shadow.{n}", f"--shadow-{n}", None, None, _NO_SHADOW) for n in (1, 2)),
    *(
        Token(f"duration.{d}", f"--duration-{d}", f"AppDuration.{d}", None, _TK_NO_MOTION)
        for d in ("instant", "fast", "base", "slow")
    ),
    *(
        Token(f"ease.{e}", f"--ease-{e}", f"AppCurve.{e}", None, _TK_NO_MOTION)
        for e in ("standard", "decelerate", "accelerate")
    ),
)

# Names a source defines that are deliberately outside the compared scales.
# Per stack, name -> reason. A silent skip is the fail-open path this closes.
_TRACKING = "Tracking is an approximate range in the freeze ('tight, e.g. -0.2px'), not a value."
EXEMPT: dict[str, dict[str, str]] = {
    "css": {
        "--tracking-display": _TRACKING,
        "--tracking-title": _TRACKING,
        "--tracking-label": _TRACKING,
        "--tracking-caption": _TRACKING,
        "--font-sans": "Font stacks are per-platform by design (DOCS-tokens.md, Typography).",
        "--font-mono": "Font stacks are per-platform by design (DOCS-tokens.md, Typography).",
        "--measure": "Web-only prose line-length cap (rule 21); no Dart/Tk text measure.",
    },
    "dart": {},
    "tk": {
        "LockSpacing.focus_thickness": "Focus-ring width (operability doc), not a scale step.",
    },
}
