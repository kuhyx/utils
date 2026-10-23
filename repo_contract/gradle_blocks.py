"""Just enough gradle (Kotlin DSL or Groovy) parsing for the launcher rules.

Not a gradle evaluator: comments are dropped, braces are matched outside
string literals, and each `{ ... }` becomes a Block whose path names its
enclosing headers (`create("sandbox")` -> `sandbox`, `release {` -> `release`).
A variant block is one directly under `buildTypes` or `productFlavors`.
Anything this cannot read as a string literal is reported as None so the
caller fails closed instead of guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

VARIANT_PARENTS = ("buildTypes", "productFlavors")
_NAMED = re.compile(
    r"""(?:create|getByName|register|maybeCreate|named)\s*(?:<[^>]*>)?\s*"""
    r"""\(\s*["']([^"']+)["']\s*\)\s*$"""
)
_IDENT = re.compile(r"([A-Za-z_]\w*)\s*$")
_SUFFIX = re.compile(r"\bapplicationIdSuffix\b")
_MAP = re.compile(
    r"manifestPlaceholders\s*(?:\+=|=|\.\s*putAll\s*\()\s*"
    r"(?:mutableMapOf|mapOf|hashMapOf)?\s*[\[(]([^\])]*)[\])]"
)


@dataclass(frozen=True)
class Block:
    """One `{ ... }`: its header path, start offset, and its own text."""

    path: tuple[str, ...]
    start: int
    body: str


def _string_end(text: str, i: int) -> int:
    """Index just past the string literal opening at `i` (EOF if unclosed)."""
    quote = '"""' if text.startswith('"""', i) else text[i]
    j = i + len(quote)
    while j < len(text):
        if text[j] == "\\":
            j += 2
        elif text.startswith(quote, j):
            return j + len(quote)
        else:
            j += 1
    return len(text)


def strip_comments(text: str) -> str:
    """`text` without // and /* */ comments; string literals untouched."""
    out, i = [], 0
    while i < len(text):
        if text[i] in "\"'":
            j = _string_end(text, i)
            out.append(text[i:j])
            i = j
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = len(text) if j < 0 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = len(text) if j < 0 else j + 2
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def _header(own: list[str]) -> str:
    """Block name from the text just before its `{`."""
    tail = re.split(r"[\n;]", "".join(own))[-1]
    named = _NAMED.search(tail) or _IDENT.search(tail)
    return named.group(1) if named else "?"


def blocks(text: str) -> list[Block]:
    """Every block of a gradle script (closing order) plus the top level last."""
    clean = strip_comments(text)
    stack: list[tuple[tuple[str, ...], int, list[str]]] = [((), 0, [])]
    out: list[Block] = []
    i = 0
    while i < len(clean):
        ch = clean[i]
        if ch in "\"'":
            j = _string_end(clean, i)
            stack[-1][2].append(clean[i:j])
            i = j
            continue
        if ch == "{":
            stack.append((stack[-1][0] + (_header(stack[-1][2]),), i, []))
        elif ch == "}" and len(stack) > 1:
            path, start, own = stack.pop()
            out.append(Block(path, start, "".join(own)))
            stack[-1][2].append("\n")
        elif ch != "}":
            stack[-1][2].append(ch)
        i += 1
    while stack:
        path, start, own = stack.pop()
        out.append(Block(path, start, "".join(own)))
    return out


def variant(block: Block) -> str | None:
    """The variant a block configures (`sandbox`, `debug`), else None."""
    if len(block.path) >= 2 and block.path[-2] in VARIANT_PARENTS:
        return block.path[-1]
    return None


def where(block: Block) -> str:
    """Human label for a block: `productFlavors.sandbox`, `defaultConfig`."""
    if variant(block):
        return ".".join(block.path[-2:])
    if block.path and block.path[-1] == "defaultConfig":
        return "defaultConfig"
    return ".".join(block.path) or "top level"


def _suffixed(block: Block) -> bool:
    """Whether `block` is a variant that sets applicationIdSuffix."""
    return variant(block) is not None and bool(_SUFFIX.search(block.body))


def suffixed_variants(text: str) -> list[str]:
    """Variants whose own block sets applicationIdSuffix."""
    names = {variant(b) or "" for b in blocks(text) if _suffixed(b)}
    return sorted(names)


def _literal(text: str) -> str | None:
    """The string literal `text` starts with; None for anything else."""
    if not text or text[0] not in "\"'":
        return None
    end = text.find(text[0], 1)
    if end < 0 or "$" in text[1:end] or "\\" in text[1:end]:
        return None
    return text[1:end]


def _values(body: str, key: str) -> list[tuple[int, str | None]]:
    """(offset, literal or None) of every assignment to placeholder `key`."""
    k = re.escape(key)
    q = r"""(['"])""" + k + r"\1"
    direct = (
        rf"manifestPlaceholders\s*\[\s*{q}\s*\]\s*=\s*",
        rf"manifestPlaceholders\s*\.\s*put\s*\(\s*{q}\s*,\s*",
        rf"manifestPlaceholders\s*\.\s*{k}\s*=\s*",
    )
    found = [
        (m.start(), _literal(body[m.end() :]))
        for pattern in direct
        for m in re.finditer(pattern, body)
    ]
    pair = re.compile(r"""(?<!\w)(['"]?)""" + k + r"\1\s*(?:to\b|:)\s*")
    for m in _MAP.finditer(body):
        found += [
            (m.start(), _literal(m.group(1)[p.end() :]))
            for p in pair.finditer(m.group(1))
        ]
    return found


def _first(item: tuple[int, str | None]) -> int:
    return item[0]


def placeholder_values(
    text: str, key: str, *, unsuffixed_only: bool = False
) -> list[tuple[str, str | None]]:
    """(block label, literal or None) per assignment, by block start.

    `unsuffixed_only` drops assignments inside a suffixed variant's block.
    """
    out = []
    for block in sorted(blocks(text), key=lambda b: b.start):
        if unsuffixed_only and _suffixed(block):
            continue
        values = sorted(_values(block.body, key), key=_first)
        out += [(where(block), v) for _, v in values]
    return out
