"""The grader's answer key (TODO-coach-ui.md decision 5), from ``answer_key.json``.

Schema: ``{"problems": {"<slug>": {"design_rule", "entries", "also_accepted",
"key_requirements", "postmortem_points"}}}``, one entry per cluster problem.

* ``design_rule``: what the binding constraint forces, in one sentence.
* ``entries``: toolbox entry names (``toolbox.json``) that solve it, 1-3. Where
  the entry is a combination ("prefix sum + hash map"), naming both of its
  parts is as good as naming it.
* ``also_accepted``: further toolbox entries that are correct but not the
  intended one (sum instead of XOR for Missing Number).
* ``key_requirements``: 2-5 vocabulary properties the requirement list must
  contain. Each is a property of the ``entries``, so the intended entries
  cover all of them.
* ``postmortem_points``: 2-4 properties and method steps a good post-mortem
  names, never code.

The file is never shown to kuhy. The design rule and the points still name no
toolbox entry, because the grader's feedback is built from them and goes
through the same leak check as coach replies (``leak.leaked_names``); a test
holds that line. kuhy reviews the JSON itself, like the toolbox.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

ANSWER_KEY_PATH = Path(__file__).with_name("answer_key.json")


def load(path: Path | None = None) -> dict[str, Any]:
    """The parsed answer key; ``path`` defaults to the shipped file at call time."""
    source = ANSWER_KEY_PATH if path is None else path
    data: dict[str, Any] = json.loads(source.read_text(encoding="utf-8"))
    return data


@dataclass(frozen=True)
class Answer:
    """What a correct run of one problem looks like."""

    design_rule: str
    entries: tuple[str, ...]
    also_accepted: tuple[str, ...]
    key_requirements: tuple[str, ...]
    postmortem_points: tuple[str, ...]


def _strings(
    raw: dict[str, Any], key: str, *, optional: bool = False
) -> tuple[str, ...]:
    value = raw.get(key, [] if optional else None)
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        msg = f"{key} must be a list of strings"
        raise TypeError(msg)
    return tuple(value)


def _answer(raw: object) -> Answer:
    if not isinstance(raw, dict) or not isinstance(raw.get("design_rule"), str):
        msg = "every answer needs an object with a string design_rule"
        raise TypeError(msg)
    return Answer(
        design_rule=raw["design_rule"],
        entries=_strings(raw, "entries"),
        also_accepted=_strings(raw, "also_accepted", optional=True),
        key_requirements=_strings(raw, "key_requirements"),
        postmortem_points=_strings(raw, "postmortem_points"),
    )


def load_answers(path: Path | None = None) -> dict[str, Answer]:
    """The typed key, ``{slug: Answer}``; a malformed file raises `TypeError`."""
    problems = load(path)["problems"]
    if not isinstance(problems, dict):
        msg = "problems must map each slug to its answer"
        raise TypeError(msg)
    return {slug: _answer(raw) for slug, raw in problems.items()}
