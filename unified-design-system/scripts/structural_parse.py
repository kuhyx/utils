"""Parsers for `structural_check.py`: one per source, all fail closed.

Every parser returns `{key: raw_value}` and raises `SystemExit` when the
structure it expects is gone. Returning `{}` would make a moved file read as
"0 parsed, 0 drifted" -- the exact vacuous pass `palette_check.py` was bitten
by -- so a vanished section is an error, never a skip.
"""

from __future__ import annotations

import re

Table = dict[str, str]


def _die(msg: str) -> None:
    raise SystemExit(f"structural_check: {msg}")


def section(text: str, header: str) -> str:
    """Body of the `## <header>` section, up to the next `## ` heading."""
    m = re.search(rf"^## {re.escape(header)}.*?$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not m:
        _die(f"section '## {header}' not found; the freeze was renamed or moved")
    return m.group(1)


def parse_tokens_md(text: str) -> Table:
    """Spacing, radius, type and shadow rows from `DOCS-tokens.md`."""
    found: Table = {}
    steps = re.search(r"`([^`\n]*·[^`\n]*)`", section(text, "Spacing scale"))
    if steps:
        for name, val in re.findall(r"(\w+) (\d+)", steps.group(1)):
            found[f"space.{name}"] = val
    for name, val in re.findall(r"`(\w+) (\d+)`", section(text, "Corner radius scale")):
        found[f"radius.{name}"] = val
    for name, val in re.findall(
        r"^\|\s*`(\w+)`\s*\|\s*(\d+)\s*\|", section(text, "Typography scale"), re.M
    ):
        found[f"text.{name}"] = val
    for level, val in re.findall(
        r"Level (\d)[^`\n]*`([^`\n]+)`", section(text, "Shadow policy")
    ):
        found[f"shadow.{level}"] = val
    return found


def parse_motion_md(text: str) -> Table:
    """Duration and easing rows from `DOCS-motion.md`."""
    found: Table = {}
    row = r"^\|\s*`(\w+)`\s*\|\s*`([^`]+)`"
    for name, val in re.findall(row, section(text, "Duration"), re.M):
        found[f"duration.{name}"] = val
    for name, val in re.findall(row, section(text, "Easing"), re.M):
        found[f"ease.{name}"] = val
    return found


def parse_css(text: str) -> Table:
    """Root-scope structural custom properties from `tokens.css`.

    Everything from the first `@media` on is overrides (reduced motion, dark
    shadows); the freeze is the root block above it.
    """
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)  # prose may name tokens
    cut = text.find("@media")
    if cut == -1:
        _die("tokens.css has no @media block; cannot find the end of :root")
    decl = re.compile(
        r"(--(?:space|radius|text|shadow|duration|ease|tracking|font|measure)[a-z0-9-]*)"
        r"\s*:\s*([^;]+);"
    )
    return {
        name: value.strip()
        for name, value in decl.findall(text[:cut])
        if not value.strip().startswith("#")  # `--text`, `--text-muted`: colours
    }


def _classes(text: str, opener: str) -> list[tuple[str, str]]:
    """(name, body) of each class; `opener` is the regex that starts one."""
    parts = list(re.finditer(opener, text, re.M))
    if not parts:
        return []
    ends = [m.start() for m in parts[1:]] + [len(text)]
    return [(m.group(1), text[m.end() : end]) for m, end in zip(parts, ends, strict=True)]


def parse_dart(text: str) -> Table:
    """`static const double|Duration|Curve` members, keyed `Class.member`."""
    found: Table = {}
    member = re.compile(r"static const (?:double|Duration|Curve) (\w+) = ([^;]+);")
    for cls, body in _classes(text, r"^abstract final class (\w+)"):
        for name, value in member.findall(body):
            found[f"{cls}.{name}"] = value.strip()
    if not found:
        _die("tokens.dart has no double/Duration/Curve constants")
    return found


def parse_tk(text: str) -> Table:
    """Integer dataclass fields, keyed `Class.field`."""
    found: Table = {}
    field = re.compile(r"^ {4}(\w+):\s*int\s*=\s*(\d+)", re.M)
    for cls, body in _classes(text, r"^class (\w+)"):
        for name, value in field.findall(body):
            found[f"{cls}.{name}"] = value
    if not found:
        _die("_theme.py has no int fields; the scales moved out of it")
    return found
