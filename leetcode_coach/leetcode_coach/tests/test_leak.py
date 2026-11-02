"""Tests for the toolbox-name leak detector shared by the Stop hook and --local."""

from __future__ import annotations

import pytest

from leetcode_coach import leak, toolbox
from leetcode_coach.tests._shared import FIXTURE_TOOLBOX

BOX = toolbox.load_safe(FIXTURE_TOOLBOX)


@pytest.mark.parametrize(
    ("reply", "names"),
    [
        ("Have you tried XOR?", ["XOR"]),
        ("what does a ^ b give when a == b?", ["XOR"]),
        ("Use a Hash\n Map for it.", ["hash map"]),
        ("A dictionary would help, or the gauss SUM.", ["hash map", "sum formula"]),
        ("xorshift is a random generator?", []),
        ("What survives when every pair cancels?", []),
        ("2^3 is eight?", []),
    ],
)
def test_leaked_names(reply: str, names: list[str]) -> None:
    assert leak.leaked_names(reply, [], BOX) == names


def test_is_it_xor_is_not_bounced() -> None:
    """kuhy asked by name, so the honest answer may say it (else it loops)."""
    reply = "Yes -- XOR is the one. What does x ^ x give?"
    assert leak.leaked_names(reply, ["is it XOR?"], BOX) == []


def test_any_alias_kuhy_typed_frees_the_whole_entry() -> None:
    assert leak.leaked_names("XOR it", ["what about exclusive OR"], BOX) == []
    assert leak.leaked_names("XOR it", ["XORing is weird"], BOX) == ["XOR"]


def test_an_empty_toolbox_never_bounces() -> None:
    assert leak.leaked_names("XOR", [], toolbox.Toolbox()) == []
