"""Output comparison: exact JSON equality, float tolerance, order rules."""

from __future__ import annotations

import json
import math

TOLERANCE = 1e-5  # LeetCode accepts floating answers within 1e-5
MAX_DEPTH = 64  # real answers nest a handful of levels; deeper is hostile


class TooDeepError(ValueError):
    """A compared value nests deeper than ``MAX_DEPTH``."""


def too_deep(value: object, limit: int = MAX_DEPTH) -> bool:
    """Whether ``value`` nests lists/dicts deeper than ``limit`` (iterative)."""
    stack: list[tuple[object, int]] = [(value, 0)]
    while stack:
        node, depth = stack.pop()
        if isinstance(node, list | dict):
            if depth >= limit:
                return True
            children = node if isinstance(node, list) else node.values()
            stack.extend((child, depth + 1) for child in children)
    return False


def _as_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return value


def _key(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _deep_sorted(value: object) -> object:
    if isinstance(value, list):
        return sorted((_deep_sorted(item) for item in value), key=_key)
    return value


def _equal(expected: object, actual: object) -> bool:
    want, got = _as_number(expected), _as_number(actual)
    if want is not None and got is not None:
        return math.isclose(want, got, rel_tol=TOLERANCE, abs_tol=TOLERANCE)
    if isinstance(expected, list) and isinstance(actual, list):
        return len(expected) == len(actual) and all(
            _equal(e, a) for e, a in zip(expected, actual, strict=True)
        )
    if isinstance(expected, dict) and isinstance(actual, dict):
        return expected.keys() == actual.keys() and all(
            _equal(expected[k], actual[k]) for k in expected
        )
    return type(expected) is type(actual) and expected == actual


def _top_sorted(value: object) -> object:
    if isinstance(value, list):
        return sorted(value, key=_key)
    return value


def matches(expected: object, actual: object, order: str) -> bool:
    """Whether ``actual`` is an accepted answer for ``expected``.

    Args:
        expected: the statement's answer (JSON value).
        actual: what the solution returned (JSON value).
        order: "exact", "any" (list order free) or "deep" (nested order free too).

    Raises:
        ValueError: ``order`` is none of those.
        TooDeepError: a value nests deeper than ``MAX_DEPTH`` (the recursive
            walks below would blow the stack).
    """
    if too_deep(expected) or too_deep(actual):
        msg = f"value nested deeper than {MAX_DEPTH} levels"
        raise TooDeepError(msg)
    if order == "exact":
        return _equal(expected, actual)
    if order == "any":
        return _equal(_top_sorted(expected), _top_sorted(actual))
    if order == "deep":
        return _equal(_deep_sorted(expected), _deep_sorted(actual))
    msg = f"unknown order {order!r}"
    raise ValueError(msg)
