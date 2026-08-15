"""The canonical palette table: one row per colour, named in each stack.

Split out of `palette_check.py` to hold both files under the 250-line cap.
This module is pure data -- the parsing and comparison logic lives in the
checker. Adding a token to any stack means adding a row here; the checker's
completeness half fails on a token no row accounts for, which is what stops
this table from quietly falling behind the sources it describes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

STACKS = ("md", "css", "dart", "tk")


@dataclass(frozen=True)
class Token:
    """One canonical colour token and its name in each stack.

    A `None` name means the token is intentionally absent from that stack;
    `why` records the reason so an absence is a decision on the record rather
    than an oversight.
    """

    canonical: str
    md: str | None
    css: str | None
    dart: str | None
    tk: str | None
    why: str = ""


# The canonical palette: one row per colour, named per stack.
#
# Deliberate absences (the `None`s) and their reasons:
#   * paper/paper-raised/line-light/text-on-light/muted-on-light -- the light
#     theme. CSS carries it in a `prefers-color-scheme` block (parsed
#     separately below); Dart names them as constants; Tk has no light theme
#     at all, because a locker surface is always dark.
#   * cat-1..6 -- the categorical ramp shipped for web only. Dart and Tk have
#     no chart/tag surfaces yet. Adding one means adding it here too.
#   * on-scrim -- introduced by the web layer for translucent overlays; the
#     other two stacks have no scrim surface.
PALETTE: tuple[Token, ...] = (
    # --- neutrals, dark (all three code stacks) ---------------------------
    Token("ink", "ink", "--bg", "ink", "bg"),
    Token("ink-raised-1", "ink-raised-1", "--surface-1", "inkRaised1", "field_bg"),
    Token(
        "ink-raised-2",
        "ink-raised-2",
        "--surface-2",
        "inkRaised2",
        None,
        why="Tk gates use a single raised step (field_bg); no second elevation.",
    ),
    Token(
        "line-dark",
        "line-dark",
        "--border",
        "lineDark",
        None,
        why="Tk gates draw no borders; elevation is a fill step.",
    ),
    Token("text-on-dark", "text-on-dark", "--text", "textOnDark", "fg"),
    Token("muted-on-dark", "muted-on-dark", "--text-muted", "mutedOnDark", "muted"),
    # --- neutrals, light --------------------------------------------------
    Token(
        "paper",
        "paper",
        "--bg@light",
        "paper",
        None,
        why="Tk: locker surfaces are always dark; there is no light theme.",
    ),
    Token(
        "paper-raised",
        "paper-raised",
        "--surface-1@light",
        "paperRaised",
        None,
        why="Tk: no light theme.",
    ),
    # The light theme collapses both dark elevation steps onto one raised
    # surface: `--surface-2` is redefined to `paper-raised` rather than
    # getting a value of its own. Mapped explicitly (not exempted) so it is
    # still compared -- if either half of the pair moves, this row fails.
    Token(
        "paper-raised-2",
        "paper-raised",
        "--surface-2@light",
        "paperRaised",
        None,
        why="Light theme has one raised step; Tk has no light theme.",
    ),
    Token(
        "line-light",
        "line-light",
        "--border@light",
        "lineLight",
        None,
        why="Tk: no light theme, and no borders.",
    ),
    Token(
        "text-on-light",
        "text-on-light",
        "--text@light",
        "textOnLight",
        None,
        why="Tk: no light theme.",
    ),
    Token(
        "muted-on-light",
        "muted-on-light",
        "--text-muted@light",
        "mutedOnLight",
        None,
        why="Tk: no light theme.",
    ),
    # --- accent + semantic roles (all three) -------------------------------
    Token("accent", "accent", "--accent", "accent", "accent"),
    Token(
        "info",
        "info",
        "--info",
        "info",
        None,
        why="Tk: no informational role distinct from accent in the gates.",
    ),
    Token("success", "success", "--success", "success", "success"),
    Token("warning", "warning", "--warning", "warning", "warning"),
    Token("danger", "danger", "--danger", "danger", "danger"),
    Token("on-fill", "on-fill", "--on-fill", "onFill", "on_fill"),
    Token("focus-ring", "focus-ring", "--focus-ring", None, "focus_ring"),
    Token(
        "on-scrim",
        None,
        "--on-scrim",
        None,
        None,
        why="Web-only: no scrim/overlay surface in the Flutter or Tk layers.",
    ),
    # --- categorical ramp (web only, for now) ------------------------------
    *(
        Token(
            f"cat-{i}",
            f"cat-{i}",
            f"--cat-{i}",
            None,
            None,
            why="Ramp shipped for web only; no chart/tag surface in Dart or Tk yet.",
        )
        for i in range(1, 7)
    ),
)

# Tokens a source legitimately defines that are not colours in the palette --
# structural/typographic values checked by the scale check, not the hex check.
NON_COLOUR_CSS = re.compile(
    r"^--(radius|space|text|tracking|font|measure|shadow)-|^--(font-sans|font-mono|measure)$"
)
