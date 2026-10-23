"""Tests for the card shape rules the /leetcode builder enforces."""

from __future__ import annotations

import pytest

from leetcode_coach import card_rules


def _card(front: str, back: str = "x") -> dict[str, str]:
    return {"front": front, "back": back}


@pytest.mark.parametrize(
    ("front", "back", "error"),
    [
        ("JS: nest or separate loops?", "Nest.", "either/or"),
        ("JS: setTimeout — built in, or do you write them?", "built in", "either/or"),
        ("JS: does clearTimeout stop a running fn?", "No", "yes/no"),
        ("JS: code after setTimeout — has cb run yet?", "No", "yes/no"),
        ("TS: Why does it break? What's the fix?", "closure", "two questions"),
        ("TS: return a function?", "return function(p) { ... }", "placeholder"),
        ("TS: return a function?", "return f …", "placeholder"),
    ],
)
def test_shape_rejects_coin_flips_and_placeholders(
    front: str, back: str, error: str
) -> None:
    assert any(error in e for e in card_rules.validate("s", [_card(front, back)]))


@pytest.mark.parametrize(
    ("front", "back"),
    [
        ("JS: What does XOR (^) return for different bits vs same?", "1 if different"),
        ("JS: write a regex matching every 'cat' or 'dog' in a string.", "/cat|dog/g"),
        ("TS: a loop runs while(a || b) — which nodes get skipped?", "leaves"),
        ("JS: call fn with the array as separate arguments?", "fn(...args)"),
        ("TS: one cur pointer walks one path. To visit all, add what?", "a stack"),
    ],
)
def test_shape_accepts_real_questions(front: str, back: str) -> None:
    assert card_rules.validate("s", [_card(front, back)]) == []


def test_validate_counts_lengths_and_slug() -> None:
    errors = card_rules.validate(
        "", [_card("q?", "one two three four five six seven eight nine")]
    )
    assert any("back is 9 words" in e for e in errors)
    assert "missing slug" in errors
    assert card_rules.validate("s", []) == ["0 cards; want 1-6"]
    assert card_rules.validate("s", [_card("", "")]) == ["card 1: empty front or back"]
    long_front = " ".join(["w"] * 21) + "?"
    assert any(
        "front is 21 words" in e for e in card_rules.validate("s", [_card(long_front)])
    )
    assert any("newlines" in e for e in card_rules.validate("s", [_card("a\nb?")]))


def test_table_escapes_pipes_and_fields_escape_html() -> None:
    cards = [_card("JS: a<b and x|y?", "n & m")]
    assert "| JS: a<b and x\\|y? | n & m |" in card_rules.table(cards)
    assert card_rules.escaped(cards) == [
        {"front": "JS: a&lt;b and x|y?", "back": "n &amp; m"}
    ]
