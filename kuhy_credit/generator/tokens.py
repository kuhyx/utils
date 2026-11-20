"""Read the few design tokens the credit panel needs from tokens.css.

tokens.css is the web stack's copy of unified-design-system; palette_check
already keeps it equal to the Dart and Tk copies, so reading this one file is
reading the shared token set.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_ROOT = re.compile(r"^:root\s*\{(.*?)^\}", re.DOTALL | re.MULTILINE)
_LIGHT = re.compile(r"@media \(prefers-color-scheme: light\)\s*\{\s*:root\s*\{(.*?)\}", re.DOTALL)
_VAR = re.compile(r"(--[a-z0-9-]+):\s*([^;]+);")
_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


@dataclass(frozen=True)
class Palette:
    """Panel colours for one theme."""

    surface: str
    border: str
    text: str


@dataclass(frozen=True)
class Tokens:
    """Both palettes plus the theme-free sizes, in px."""

    dark: Palette
    light: Palette
    focus: str
    radius: int
    space_sm: int
    space_md: int
    text_body: int


def _vars(block: str) -> dict[str, str]:
    return {k: v.strip() for k, v in _VAR.findall(block)}


def _get(table: dict[str, str], name: str) -> str:
    if name not in table:
        msg = f"tokens.css has no {name}"
        raise ValueError(msg)
    return table[name]


def _palette(table: dict[str, str]) -> Palette:
    return Palette(_get(table, "--surface-1"), _get(table, "--border"), _get(table, "--text"))


def _px(table: dict[str, str], name: str) -> int:
    return int(_get(table, name).removesuffix("px"))


def parse_tokens(css: str) -> Tokens:
    """Parse the dark default and the light override out of tokens.css."""
    css = _COMMENT.sub("", css)
    root_match = _ROOT.search(css) or re.search(r":root\s*\{(.*?)\}", css, re.DOTALL)
    root = _vars(root_match.group(1)) if root_match else {}
    light_match = _LIGHT.search(css)
    light = {**root, **_vars(light_match.group(1) if light_match else "")}
    return Tokens(
        dark=_palette(root),
        light=_palette(light),
        focus=_get(root, "--focus-ring"),
        radius=_px(root, "--radius-md"),
        space_sm=_px(root, "--space-2"),
        space_md=_px(root, "--space-3"),
        text_body=_px(root, "--text-body"),
    )
