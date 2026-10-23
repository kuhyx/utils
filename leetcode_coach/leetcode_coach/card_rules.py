"""The shape rules every /leetcode post-mortem card must pass.

Short by construction: a back longer than BACK_MAX_WORDS words or a front
longer than FRONT_MAX_WORDS fails the run and names the offender, so the model
has to shorten instead of shipping a paragraph. Shape is gated the same way: a
yes/no or either/or question is a coin flip, two questions on one front split
the recall, and a `{ ... }` back is a placeholder, not an answer.

Split out of `make_cards.py` (which keeps the delivery side) for the
250-line cap; the rules are unchanged.
"""

from __future__ import annotations

import html
import re

FRONT_MAX_WORDS = 20
BACK_MAX_WORDS = 8
MIN_CARDS, MAX_CARDS = 1, 6
YES_NO = re.compile(
    r"(is|are|does|do|did|can|could|should|will|would|has|have|was|were)\b",
    re.IGNORECASE,
)
EITHER_OR = re.compile(r"\bor\b", re.IGNORECASE)
PLACEHOLDER = re.compile(r"\{\s*(\.\.\.|…)\s*\}|…")

Card = dict[str, str]


def shape_errors(i: int, front: str, back: str) -> list[str]:
    """Coin-flip and placeholder cards: a pass on them proves no recall."""
    errors: list[str] = []
    if front.count("?") > 1:
        errors.append(f"card {i}: two questions on one front; split it")
    question = re.split(r"[:—]|\.\s", front)[-1].strip()
    if question.endswith("?"):
        if YES_NO.match(question):
            errors.append(f"card {i}: yes/no front; ask for the thing itself")
        elif EITHER_OR.search(question):
            errors.append(f"card {i}: either/or front; the back is a coin flip")
    if PLACEHOLDER.search(back):
        errors.append(f"card {i}: placeholder in back; write the real code")
    return errors


def validate(slug: str, cards: list[Card]) -> list[str]:
    """Return every rule violation as a human-readable line (empty = ok)."""
    errors: list[str] = []
    if not MIN_CARDS <= len(cards) <= MAX_CARDS:
        errors.append(f"{len(cards)} cards; want {MIN_CARDS}-{MAX_CARDS}")
    for i, c in enumerate(cards, 1):
        front, back = str(c.get("front", "")).strip(), str(c.get("back", "")).strip()
        if not front or not back:
            errors.append(f"card {i}: empty front or back")
            continue
        if "\n" in front or "\n" in back:
            errors.append(f"card {i}: newlines are not allowed")
        if len(front.split()) > FRONT_MAX_WORDS:
            errors.append(
                f"card {i}: front is {len(front.split())} words (max {FRONT_MAX_WORDS})"
            )
        if (n := len(back.split())) > BACK_MAX_WORDS:
            errors.append(
                f"card {i}: back is {n} words (max {BACK_MAX_WORDS}): {back!r}"
            )
        errors += shape_errors(i, front, back)
    if not slug:
        errors.append("missing slug")
    return errors


def _cell(text: str) -> str:
    """Markdown table cell: a bare pipe would split it in two."""
    return text.strip().replace("|", "\\|")


def _esc(text: str) -> str:
    """HTML-escape one field (quotes are left alone)."""
    return html.escape(text.strip(), quote=False)


def table(cards: list[Card]) -> str:
    """Markdown table for the chat reply, so the model relays instead of retyping."""
    rows = ["| Front | Back |", "|---|---|"]
    rows += [f"| {_cell(c['front'])} | {_cell(c['back'])} |" for c in cards]
    return "\n".join(rows)


def escaped(cards: list[Card]) -> list[Card]:
    """Anki fields are HTML: escape so `a<b` or `&` survive rendering."""
    return [{"front": _esc(c["front"]), "back": _esc(c["back"])} for c in cards]
