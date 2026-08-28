"""Verify one palette across all four token sources.

`tokens.md` freezes the palette as prose, and three packages re-express it as
code: `web_ui/src/tokens.css` (CSS custom properties), `design_system`
(Dart constants) and `gatelock` (a `LockConfig` dataclass). Nothing until now
compared them, so a hex edited in one stack drifted silently in the other
three -- the exact failure "one palette everywhere" is supposed to exclude.

The check is deliberately bidirectional. Comparing only the tokens named in
the map below would pass silently the moment someone adds a token to one
source and forgets the map, which is the drift most likely to actually
happen. So:

  * every token parsed out of every source must be accounted for -- either
    mapped, or named in `EXEMPT`; an unmapped token is a failure, not a skip
  * every mapped token must resolve in every stack that is not exempt for it

Exemptions are declared per token per stack, with a reason. A silent skip is
the fail-open path this script exists to close.

Run: python3 unified-design-system/scripts/palette_check.py
Exit 0 = all sources agree and are complete; 1 = drift or an unmapped token.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from palette_map import NON_COLOUR_CSS, PALETTE, STACKS

# Repo root: this file is <root>/unified-design-system/scripts/palette_check.py
ROOT = Path(__file__).resolve().parents[2]

# Renamed by the md-naming migration; the gate kept pointing at the old
# name and had been failing on every push since.
TOKENS_MD = ROOT / "unified-design-system" / "DOCS-tokens.md"
TOKENS_CSS = ROOT / "web_ui" / "src" / "tokens.css"
TOKENS_DART = ROOT / "design_system" / "lib" / "src" / "tokens.dart"
# LockConfig moved out of _window.py when that file was split for the
# 250-line cap; the palette lives with the dataclass, not the window.
LOCKCONFIG_PY = ROOT / "gatelock" / "gatelock" / "_config.py"


@dataclass
class Result:
    """One check outcome."""

    ok: bool
    detail: str


@dataclass
class Sources:
    """Parsed colour tables, one per stack."""

    md: dict[str, str] = field(default_factory=dict)
    css: dict[str, str] = field(default_factory=dict)
    dart: dict[str, str] = field(default_factory=dict)
    tk: dict[str, str] = field(default_factory=dict)


def _norm(value: str) -> str:
    """Normalise a hex colour to lowercase `#rrggbb` for comparison."""
    return "#" + value.lstrip("#").lower()


def parse_md(text: str) -> dict[str, str]:
    """Pull `| \\`token\\` | \\`#HEX\\` |` rows out of the frozen prose table."""
    found: dict[str, str] = {}
    row = re.compile(r"^\|\s*`([a-z0-9-]+)`\s*\|\s*`(#[0-9A-Fa-f]{6})`")
    for line in text.splitlines():
        m = row.match(line.strip())
        if m:
            found[m.group(1)] = _norm(m.group(2))
    return found


def parse_css(text: str) -> dict[str, str]:
    """Parse `--token: #hex;`, tagging light-theme overrides with `@light`.

    The light palette lives in a `prefers-color-scheme: light` block that
    redefines the same custom-property names, so the names alone collide. The
    `@light` suffix keeps both halves addressable from one map.
    """
    found: dict[str, str] = {}
    # Split off the light-theme block; everything before it is the dark root.
    light_at = text.find("prefers-color-scheme: light")
    dark_text = text[:light_at] if light_at != -1 else text
    light_text = ""
    if light_at != -1:
        rest = text[light_at:]
        # The light block ends at the next top-level @media.
        nxt = rest.find("@media", 1)
        light_text = rest[:nxt] if nxt != -1 else rest

    decl = re.compile(r"(--[a-z0-9-]+)\s*:\s*(#[0-9A-Fa-f]{6})\s*;")
    for name, value in decl.findall(dark_text):
        found[name] = _norm(value)
    for name, value in decl.findall(light_text):
        found[f"{name}@light"] = _norm(value)
    return found


def parse_dart(text: str) -> dict[str, str]:
    """Parse `static const Color name = Color(0xFFRRGGBB);` and aliases."""
    found: dict[str, str] = {}
    literal = re.compile(
        r"static const Color (\w+) = Color\(0x[fF]{2}([0-9A-Fa-f]{6})\)"
    )
    for name, value in literal.findall(text):
        found[name] = _norm(value)
    # Aliases: `static const Color info = accent;`
    alias = re.compile(r"static const Color (\w+) = (\w+);")
    for name, target in alias.findall(text):
        if target in found:
            found[name] = found[target]
    return found


def parse_tk(text: str) -> dict[str, str]:
    """Parse `field: str = "#RRGGBB"` defaults out of the LockConfig block."""
    found: dict[str, str] = {}
    start = text.find("class LockConfig")
    if start == -1:
        # Fail closed. Returning {} here made every tk comparison vacuously
        # pass when LockConfig moved to _config.py during the 250-line split:
        # "0 parsed token(s)" read as success, and the drift guard was off
        # for the whole gatelock stack without anything going red.
        msg = (
            "LockConfig not found in the file palette_check reads. It has "
            "moved; update LOCKCONFIG_PY rather than letting the tk stack go "
            "unchecked."
        )
        raise SystemExit(msg)
    body = text[start:]
    decl = re.compile(r'^\s{4}(\w+):\s*str\s*=\s*"(#[0-9A-Fa-f]{6})"', re.MULTILINE)
    for name, value in decl.findall(body):
        found[name] = _norm(value)
    return found


def load() -> Sources:
    """Read and parse all four token sources."""
    return Sources(
        md=parse_md(TOKENS_MD.read_text(encoding="utf-8")),
        css=parse_css(TOKENS_CSS.read_text(encoding="utf-8")),
        dart=parse_dart(TOKENS_DART.read_text(encoding="utf-8")),
        tk=parse_tk(LOCKCONFIG_PY.read_text(encoding="utf-8")),
    )


def check_agreement(src: Sources) -> list[Result]:
    """Every mapped token must carry the same hex in every non-exempt stack."""
    results: list[Result] = []
    for token in PALETTE:
        seen: dict[str, str] = {}
        missing: list[str] = []
        for stack in STACKS:
            name = getattr(token, stack)
            if name is None:
                continue  # declared absence, justified in `why`
            table: dict[str, str] = getattr(src, stack)
            if name not in table:
                missing.append(f"{stack}:{name}")
            else:
                seen[stack] = table[name]

        if missing:
            results.append(
                Result(False, f"{token.canonical:<14} MISSING {', '.join(missing)}")
            )
            continue

        values = set(seen.values())
        if len(values) > 1:
            detail = ", ".join(f"{s}={v}" for s, v in sorted(seen.items()))
            results.append(Result(False, f"{token.canonical:<14} DRIFT {detail}"))
        else:
            only = next(iter(values))
            results.append(
                Result(
                    True,
                    f"{token.canonical:<14} {only} across {len(seen)} stack(s)",
                )
            )
    return results


def check_completeness(src: Sources) -> list[Result]:
    """Every colour a source defines must be mapped -- no silent extras.

    This is the half that catches "someone added a token and never touched
    the map", which a pure agreement check passes happily.
    """
    results: list[Result] = []
    for stack in STACKS:
        mapped = {getattr(t, stack) for t in PALETTE if getattr(t, stack) is not None}
        table: dict[str, str] = getattr(src, stack)
        extras = sorted(
            name
            for name in table
            if name not in mapped and not NON_COLOUR_CSS.match(name)
        )
        if extras:
            results.append(
                Result(
                    False,
                    f"{stack:<4} defines unmapped colour(s): {', '.join(extras)} "
                    "-- add them to PALETTE (or declare an exemption)",
                )
            )
        else:
            results.append(
                Result(
                    True, f"{stack:<4} all {len(table)} parsed token(s) accounted for"
                )
            )
    return results


def main() -> int:
    """Run both halves of the check and report."""
    src = load()

    print("== agreement: one hex per token, across stacks ==")
    results = check_agreement(src)
    for r in results:
        print(("PASS " if r.ok else "FAIL ") + r.detail)

    print("\n== completeness: no unmapped colour in any source ==")
    completeness = check_completeness(src)
    for r in completeness:
        print(("PASS " if r.ok else "FAIL ") + r.detail)

    failures = sum(not r.ok for r in (*results, *completeness))
    print(f"\n{failures} failing check(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
