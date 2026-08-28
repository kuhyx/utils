"""Does a range constraint admit a given version?

Only used for the toolchain declarations, where a range is legitimate: an app
saying `sdk: ^3.12.2` is not stale just because Dart moved to 3.13.2 — that
constraint already permits it. The meaningful question there is whether the
range *excludes* the current toolchain, which is a real, actionable break.

Deliberately small: caret, tilde and the comparison operators cover every
constraint style present in these repos. Anything unrecognised returns True,
because a checker that guesses "violation" on syntax it does not understand
produces exactly the red-for-no-reason the gate must avoid.
"""

from __future__ import annotations

import re

from dep_freshness.versions import parse

_OP = re.compile(r"(>=|<=|==|!=|\^|~>|~|>|<)?\s*([0-9][0-9A-Za-z.\-+*]*)")
_ANY = frozenset({"", "any", "*", "latest"})


def _upper_for_caret(text: str) -> str:
    """Caret's exclusive upper bound: `^1.2.3` -> `2.0.0`, `^0.2.1` -> `0.3.0`.

    Dart and npm agree on the 0.x special case, and it matters: `^0.2.1` must
    not admit 0.3.0.
    """
    parts = [int(p) for p in re.split(r"[.\-+]", text)[:3] if p.isdigit()]
    while len(parts) < 3:
        parts.append(0)
    major, minor, _ = parts
    if major > 0:
        return f"{major + 1}.0.0"
    if minor > 0:
        return f"0.{minor + 1}.0"
    return f"0.0.{parts[2] + 1}"


def _clause(operator: str | None, bound: str, version) -> bool:
    other = parse(bound)
    if other is None:
        return True
    if operator == "^":
        upper = parse(_upper_for_caret(bound))
        return version >= other and (upper is None or version < upper)
    if operator in ("~", "~>"):
        upper = parse(f"{other.major}.{other.minor + 1}.0")
        return version >= other and (upper is None or version < upper)
    if operator == ">=":
        return version >= other
    if operator == "<=":
        return version <= other
    if operator == ">":
        return version > other
    if operator == "<":
        return version < other
    if operator == "!=":
        return version != other
    return version == other  # bare or `==`


def satisfies(constraint: str, candidate: str) -> bool:
    """True when `candidate` falls inside `constraint`."""
    text = str(constraint or "").strip().strip('"').strip("'")
    if text.lower() in _ANY:
        return True
    version = parse(candidate)
    if version is None:
        return True
    clauses = [c for c in _OP.finditer(text)]
    if not clauses:
        return True
    return all(_clause(m.group(1), m.group(2), version) for m in clauses)


def lower_bound(constraint: str) -> str | None:
    """The smallest version a constraint admits, when it states one."""
    text = str(constraint or "").strip()
    match = re.match(r"\s*(\^|~>|~|>=|==)?\s*([0-9][0-9A-Za-z.\-+]*)", text)
    if not match:
        return None
    return match.group(2)
