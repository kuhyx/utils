"""The statement's worked examples and the starter's function name (run_code).

The statement is ``fetch_problem.render(q, "javascript")`` markdown. LeetCode
writes an example in three shapes, all handled by one line scan: bold labels
on plain lines (``**Input:** nums = [3,0,1]``), the same with the values in
code spans, and the same inside a ``` fence. An ``Input:`` line is
``name = <json>`` pairs split on top-level commas; the following ``Output:``
line closes the example. A value that is not JSON (a linked list drawn as
``1->2``, a design problem's call list) skips that example with a warning:
running kuhy's code against a guessed input would report a wrong "got".

Examples are numbered by their place in the statement, so "example 3" is the
one kuhy reads as Example 3 even when an earlier one was skipped. Only the
body counts: the starter code and the site hints come after the first
``## `` heading and are never scanned for examples.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import re
from typing import Final

_logger: Final = logging.getLogger(__name__)

_NAME_RES: Final = (
    re.compile(r"\b(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:function\b|\()"),
    re.compile(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\("),
)
_LABEL: Final = re.compile(r"^(Input|Output)\s*:\s*(.*)$")
_PAIR: Final = re.compile(r"^([A-Za-z_]\w*)\s*=\s*(.+)$", re.DOTALL)
_STARTER: Final = "## Starter code"
_OPENERS: Final = {"[": "]", "{": "}", "(": ")"}


@dataclass(frozen=True)
class Example:
    """One worked example: its number, the call's arguments, the answer."""

    n: int
    args: tuple[object, ...]
    expected: object


def function_name(statement: str) -> str | None:
    """The function the starter code declares (starter section first)."""
    starter = statement.split(_STARTER, 1)
    for text in (starter[-1], statement):
        for pattern in _NAME_RES:
            if match := pattern.search(text):
                return match.group(1)
    return None


def split_top_level(text: str) -> list[str]:
    """``text`` split on commas outside brackets and string literals."""
    parts: list[str] = []
    depth = 0
    quoted = escaped = False
    start = 0
    for i, ch in enumerate(text):
        if escaped:
            escaped = False
        elif quoted:
            escaped = ch == "\\"
            quoted = ch != '"'
        elif ch == '"':
            quoted = True
        elif ch in _OPENERS:
            depth += 1
        elif ch in _OPENERS.values():
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(text[start:i])
            start = i + 1
    parts.append(text[start:])
    return [p.strip() for p in parts]


def _arguments(text: str) -> tuple[object, ...]:
    """The values of ``a = 1, b = [2]``; ValueError when one is not JSON."""
    values: list[object] = []
    for part in split_top_level(text):
        match = _PAIR.match(part)
        if match is None:
            msg = f"not a name = value pair: {part[:40]!r}"
            raise ValueError(msg)
        values.append(json.loads(match.group(2)))
    return tuple(values)


def _clean(line: str) -> str:
    """A line without markdown emphasis, code ticks and (nb)spaces around it."""
    return line.replace("**", "").replace("`", "").strip()


def _labels(body: str) -> list[tuple[str, str]]:
    """Every ``(Input|Output, value)`` line of the body, in order."""
    matches = (_LABEL.match(_clean(raw)) for raw in body.splitlines())
    return [(m.group(1), m.group(2).strip()) for m in matches if m is not None]


def _body(statement: str) -> str:
    """The statement above its first ``## `` section (starter, hints)."""
    return re.split(r"^## ", statement, maxsplit=1, flags=re.MULTILINE)[0]


def parse(statement: str) -> tuple[str | None, list[Example]]:
    """The starter's function name and every example that parses."""
    found: list[Example] = []
    pending: str | None = None
    number = 0
    for label, value in _labels(_body(statement)):
        if label == "Input":
            pending = value
            continue
        if pending is None:
            continue
        number += 1
        try:
            found.append(Example(number, _arguments(pending), json.loads(value)))
        except ValueError as exc:
            _logger.warning("example %d skipped, not runnable: %s", number, exc)
        pending = None
    return function_name(statement), found
