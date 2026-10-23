"""Steps 1 and 5 on a cheap model; the feedback rules every grade obeys.

Same route as the requirement checker (`req_check.ask_models`): haiku with no
tools, then Ollama, and when neither answers the step passes ``unverified``
(fail open: a grader outage must never wall kuhy in). The answer key goes to
the grader and nowhere else, so feedback is checked mechanically before it is
shown: it may not name a toolbox entry kuhy has not named yet (until the
first code, `leak.leaked_names`), and it may not quote the key (any run of
`QUOTE_WORDS` words from it). A failing feedback is replaced by the plain
missing-property line.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import TYPE_CHECKING, Any, Final

from leetcode_coach import leak, req_check

if TYPE_CHECKING:
    from collections.abc import Callable

    from leetcode_coach.answer_key import Answer
    from leetcode_coach.toolbox import Toolbox

GRADES: Final = ("pass", "partial", "fail")
QUOTE_WORDS: Final = 5
POSTMORTEM_STEP: Final = 5
UNVERIFIED: Final = "Not checked: the grader could not be reached, so this step counts."
CONSTRAINT_HINT: Final = "Name the limit that binds and say what it rules out."
_RULES: Final = (
    'Reply with ONE JSON object and nothing else: {"grade": "pass" | '
    '"partial" | "fail", "feedback": "<one or two sentences>"}. The feedback '
    "names what is missing as a property of a good answer. Never name an "
    "operation, a data structure or an algorithm, never give the solution, and "
    "never quote or paraphrase the reference: it is secret."
)
CONSTRAINT_SYSTEM: Final = (
    "You grade one step of a student's method for a programming problem: "
    "naming the binding constraint and what it forces. pass = the answer names "
    "the limit that binds and what it rules out or forces; partial = only one "
    "of the two; fail = neither. " + _RULES
)
POSTMORTEM_SYSTEM: Final = (
    "You grade a student's post-mortem, written after solving a programming "
    "problem: which properties of the operation did the work, and how they "
    "could have found it from the constraints. pass = it names the key "
    "properties and at least one of the reference points; partial = some of "
    "them; fail = none. Property names from the key list may be used in the "
    "feedback. " + _RULES
)


@dataclass(frozen=True)
class Grade:
    """One grader answer."""

    grade: str
    feedback: str
    via: str


def _valid(obj: dict[str, Any] | None) -> Grade | None:
    if obj is None or obj.get("grade") not in GRADES:
        return None
    feedback = obj.get("feedback", "")
    if not isinstance(feedback, str):
        return None
    return Grade(str(obj["grade"]), feedback.strip(), "")


def _prompt(step: int, statement: str, answer: str, key: Answer) -> str:
    if step == 1:
        reference = f"## Reference rule (secret)\n{key.design_rule}"
    else:
        points = "\n".join(f"- {p}" for p in key.postmortem_points)
        reference = (
            f"## Reference (secret)\nRule: {key.design_rule}\n"
            f"Key properties: {', '.join(key.key_requirements)}\nPoints:\n{points}"
        )
    return (
        f"## Problem\n{statement.strip()}\n\n{reference}\n\n"
        f"## Student's answer\n{answer.strip()}\n"
    )


def model_grade(
    step: int,
    statement: str,
    answer: str,
    key: Answer,
    ask: Callable[..., dict[str, Any]] | None,
) -> Grade:
    """Grade step 1 (constraint) or 5 (post-mortem); ``unverified`` pass if down."""
    system = CONSTRAINT_SYSTEM if step == 1 else POSTMORTEM_SYSTEM
    got = req_check.ask_models(
        system, _prompt(step, statement, answer, key), _valid, ask
    )
    if got is None:
        return Grade("pass", UNVERIFIED, "unverified")
    grade, via = got
    return Grade(grade.grade, grade.feedback, via)


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def quotes_key(feedback: str, key: Answer) -> bool:
    """Whether `feedback` repeats `QUOTE_WORDS` consecutive words of the key."""
    said = " ".join(_words(feedback))
    for source in (key.design_rule, *key.postmortem_points):
        words = _words(source)
        for i in range(len(words) - QUOTE_WORDS + 1):
            if " ".join(words[i : i + QUOTE_WORDS]) in said:
                return True
    return False


def fallback(step: int, key: Answer) -> str:
    """The plain missing-property line a rejected feedback becomes."""
    if step == POSTMORTEM_STEP:
        return "Say which properties did the work: " + ", ".join(key.key_requirements)
    return CONSTRAINT_HINT


def safe_feedback(  # pylint: disable=too-many-arguments
    feedback: str,
    *,
    step: int,
    key: Answer,
    box: Toolbox,
    kuhy_texts: list[str],
    code_seen: bool,
) -> str:
    """`feedback`, or `fallback` when it names an entry early or quotes the key."""
    early = not code_seen and leak.leaked_names(feedback, kuhy_texts, box)
    if early or quotes_key(feedback, key):
        return fallback(step, key)
    return feedback
