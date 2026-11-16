# Copyright (c) 2026 Krzysztof Rudnicki. MIT License.
"""Which RTDB paths of an app's tree are clear, sealed units, or structure.

The tree keeps its shape: keys stay clear so ``orderBy="$key"``, PATCH and
SSE paths work unchanged. Every *unit* (a node one writer writes whole,
below which nothing is written) is stored sealed; a unit may keep a few
clear siblings (server timestamps RTDB must resolve). ``clear`` prefixes
hold ids, counters and lease times only. Any other path is refused by the
sealer (fail closed), so a new node cannot go out in plaintext by accident.

Patterns are ``/``-separated; ``*`` matches one segment.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class E2eLayoutError(ValueError):
    """A write the layout has no rule for, or one below a sealed unit."""


def parts_of(path: str) -> list[str]:
    """``path``'s segments (no empty ones)."""
    return [p for p in path.split("/") if p]


def _matches(pattern: list[str], parts: list[str]) -> bool:
    return len(pattern) == len(parts) and all(
        p in {"*", q} for p, q in zip(pattern, parts, strict=True)
    )


@dataclass(frozen=True)
class Rule:
    """Where ``parts`` falls: ``clear``, ``unit``, ``below``, ``struct``, ``unknown``.

    ``depth`` is the unit's length for ``below``; ``keep`` the clear fields
    of a unit.
    """

    kind: str
    depth: int = 0
    keep: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Layout:
    """An app's tree rules: ``root`` (e.g. ``tutor/v1-e2e``) plus patterns.

    ``clear`` patterns cover their whole subtree; ``units`` map a unit
    pattern to the clear fields it keeps beside the sealed blob.
    """

    root: str
    clear: tuple[str, ...]
    units: dict[str, frozenset[str]] = field(default_factory=dict)

    def classify(self, parts: list[str]) -> Rule:
        """The rule for the node at ``parts`` (relative to :attr:`root`)."""
        for pattern in self.clear:
            pat = pattern.split("/")
            if len(pat) <= len(parts) and _matches(pat, parts[: len(pat)]):
                return Rule("clear")
        for pattern, keep in self.units.items():
            pat = pattern.split("/")
            if _matches(pat, parts):
                return Rule("unit", len(pat), keep)
            if len(pat) < len(parts) and _matches(pat, parts[: len(pat)]):
                return Rule("below", len(pat), keep)
        for pattern in (*self.clear, *self.units):
            pat = pattern.split("/")
            if len(parts) < len(pat) and _matches(pat[: len(parts)], parts):
                return Rule("struct")
        return Rule("unknown")

    def unit_path(self, path: str) -> str | None:
        """The sealed unit ``path`` lies strictly below, or ``None``."""
        parts = parts_of(path)
        rule = self.classify(parts)
        return "/".join(parts[: rule.depth]) if rule.kind == "below" else None
