"""Output comparison: exact JSON equality, float tolerance, order rules."""

from __future__ import annotations

import json
import math

TOLERANCE = 1e-5  # LeetCode accepts floating answers within 1e-5


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
    """
    if order == "exact":
        return _equal(expected, actual)
    if order == "any":
        return _equal(_top_sorted(expected), _top_sorted(actual))
    if order == "deep":
        return _equal(_deep_sorted(expected), _deep_sorted(actual))
    msg = f"unknown order {order!r}"
    raise ValueError(msg)
