from __future__ import annotations

import ast
import json
import logging
import re
from typing import Final

from code_runner._model import Example, Order
from code_runner._split import split_top_level

_logger: Final = logging.getLogger(__name__)
_LABEL: Final = re.compile(r"^(Input|Output)\s*:\s*(.*)$")
_PAIR: Final = re.compile(r"^([A-Za-z_]\w*)\s*=\s*(.+)$", re.DOTALL)
_ANY_ORDER: Final = re.compile(r"any order|order of the output", re.IGNORECASE)
_DEEP_ORDER: Final = re.compile(
    r"order of the (?:triplets|quadruplets|subsets|groups|pairs|elements)",
    re.IGNORECASE,
)


def _value(text: str) -> object:
    try:
        return json.loads(text)
    except ValueError:
        try:
            return ast.literal_eval(text)
        except (ValueError, SyntaxError) as exc:
            raise ValueError(text[:40]) from exc


def _arguments(text: str) -> dict[str, object]:
    args: dict[str, object] = {}
    for part in split_top_level(text):
        pair = _PAIR.match(part)
        if pair is None:
            msg = f"not a name = value pair: {part[:40]!r}"
            raise ValueError(msg)
        args[pair.group(1)] = _value(pair.group(2))
    return args


def _labels(body: str) -> list[tuple[str, str]]:
    cleaned = (
        line.replace("**", "").replace("`", "").strip() for line in body.splitlines()
    )
    matched = (_LABEL.match(line) for line in cleaned)
    return [(m.group(1), m.group(2).strip()) for m in matched if m is not None]


def _order(body: str) -> Order:
    if _DEEP_ORDER.search(body):
        return "deep"
    return "any" if _ANY_ORDER.search(body) else "exact"


def parse_examples(statement: str) -> list[Example]:
    body = re.split(r"^## ", statement, maxsplit=1, flags=re.MULTILINE)[0]
    order = _order(body)
    found: list[Example] = []
    pending: str | None = None
    number = 0
    for label, text in _labels(body):
        if label == "Input":
            pending = text
            continue
        if pending is None:
            continue
        number += 1
        try:
            found.append(Example(number, _arguments(pending), _value(text), order))
        except ValueError as exc:
            _logger.warning("example %d skipped, not runnable: %s", number, exc)
        pending = None
    return found
