"""Tests for the toolbox (decision 9) and its property cards (decision 11).

The card front lists an entry's properties, so two entries whose property sets
nest would give a card with two right answers; the shape test rules that out.
"""

from __future__ import annotations

import io
import json
import shutil
from typing import TYPE_CHECKING

import pytest

from leetcode_coach import card_rules, progress, toolbox, toolbox_cards

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def box(tmp_path: Path) -> Path:
    """A private copy of the shipped toolbox, safe to append to."""
    copy = tmp_path / "toolbox.json"
    shutil.copy(toolbox.TOOLBOX_PATH, copy)
    return copy


def test_every_property_is_in_the_vocabulary_and_explained() -> None:
    data = toolbox.load()
    vocab = data["properties"]
    assert all(isinstance(m, str) and m.strip() for m in vocab.values())
    for entry in data["entries"]:
        assert entry["properties"], entry["name"]
        assert set(entry["properties"]) <= set(vocab), entry["name"]
    used = {p for e in data["entries"] for p in e["properties"]}
    assert used == set(vocab)


def test_names_and_aliases_are_unique() -> None:
    names = [
        n.casefold()
        for e in toolbox.load()["entries"]
        for n in [e["name"], *e["aliases"]]
    ]
    assert len(names) == len(set(names))


def test_no_property_meaning_names_an_entry() -> None:
    # The incomplete-list note shows meanings to kuhy before code; one that
    # says "a ^ x ^ x = a" hands over the answer it is asking him to find.
    box = toolbox.load()
    names = {n.casefold() for e in box["entries"] for n in [e["name"], *e["aliases"]]}
    leaks = {
        prop: hit
        for prop, meaning in box["properties"].items()
        for hit in names | {"^", "&", "sort"}
        if hit in meaning.casefold()
    }
    assert leaks == {}


def test_no_name_is_a_cluster_problem_title() -> None:
    # The leak bounce fires on any entry name or alias before the first code
    # event, so one that is a problem's own title bounces its restatement.
    titles = {
        p["slug"].replace("-", " ")
        for problems in progress.load_clusters().values()
        for p in problems
    }
    for entry in toolbox.load()["entries"]:
        for name in [entry["name"], *entry["aliases"]]:
            assert name.casefold() not in titles, name


def test_no_entry_property_set_nests_inside_another() -> None:
    entries = toolbox.load()["entries"]
    assert len(entries) >= 20
    for a in entries:
        for b in entries:
            if a is not b:
                assert not set(a["properties"]) <= set(b["properties"]), (
                    a["name"],
                    b["name"],
                )


@pytest.mark.parametrize(
    "name",
    [
        "XOR",
        "per-bit counts mod k",
        "Boyer-Moore majority vote",
        "two pointers",
        "sliding window",
        "prefix sums",
        "prefix sum + hash map",
        "monotonic stack",
        "sort by start + merge",
        "sort by end + greedy pick",
        "heap",
    ],
)
def test_the_seeded_clusters_are_covered(name: str) -> None:
    assert toolbox_cards.find(toolbox.load(), name)["name"] == name


def test_every_entry_makes_a_valid_property_card() -> None:
    entries = toolbox.load()["entries"]
    cards = [toolbox_cards.entry_card(e) for e in entries]
    for start in range(0, len(cards), card_rules.MAX_CARDS):
        chunk = cards[start : start + card_rules.MAX_CARDS]
        assert card_rules.validate(toolbox_cards.SLUG, chunk) == []
    assert cards[0] == {
        "front": "Toolbox: " + ", ".join(entries[0]["properties"]) + "?",
        "back": entries[0]["name"],
    }


def test_find_matches_aliases_case_insensitively() -> None:
    assert toolbox_cards.find(toolbox.load(), "  hash TABLE ")["name"] == "hash map"
    with pytest.raises(KeyError, match="not in the toolbox"):
        toolbox_cards.find(toolbox.load(), "segment tree")


def test_append_entry_appends_only_when_called(box: Path) -> None:
    before = box.read_text(encoding="utf-8")
    toolbox_cards.cards_for(["XOR"], box)
    assert box.read_text(encoding="utf-8") == before
    entry = toolbox_cards.append_entry(
        "trie", ["prefix tree"], ["O(1) lookup", "partial order"], path=box
    )
    data = toolbox.load(box)
    assert (
        data["entries"][-1]
        == entry
        == {
            "name": "trie",
            "aliases": ["prefix tree"],
            "properties": ["O(1) lookup", "partial order"],
        }
    )
    assert box.read_text(encoding="utf-8").endswith("\n")


@pytest.mark.parametrize(
    ("name", "aliases", "properties", "error"),
    [
        ("", [], ["greedy"], "empty name"),
        ("trie", [], [], "no properties"),
        ("trie", [], ["fast"], "unknown properties: fast"),
        ("Hash Map", [], ["greedy", "O(1) lookup"], "already in the toolbox"),
        ("trie", ["^"], ["greedy", "O(1) lookup"], "already in the toolbox"),
        ("trie", [], ["greedy"], "nests with 'sort by end"),
        ("trie", [], ["O(1) lookup", "O(1) lookup"], "listed twice"),
    ],
)
def test_append_entry_refuses_bad_entries(
    box: Path, name: str, aliases: list[str], properties: list[str], error: str
) -> None:
    before = box.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match=error):
        toolbox_cards.append_entry(name, aliases, properties, path=box)
    assert box.read_text(encoding="utf-8") == before


def test_cli_cards_prints_builder_input(capsys: pytest.CaptureFixture[str]) -> None:
    assert toolbox_cards.main(["cards", "xor", "heap"]) == 0
    spec = json.loads(capsys.readouterr().out)
    assert spec["slug"] == "toolbox"
    assert [c["back"] for c in spec["cards"]] == ["XOR", "heap"]


def test_cli_cards_unknown_name_fails(capsys: pytest.CaptureFixture[str]) -> None:
    assert toolbox_cards.main(["cards", "segment tree"]) == 1
    assert "not in the toolbox" in capsys.readouterr().err


def test_cli_add_appends_and_reports(
    box: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(toolbox, "TOOLBOX_PATH", box)
    args = ["add", "trie", "--alias", "prefix tree", "--property", "O(1) lookup"]
    assert toolbox_cards.main([*args, "--property", "partial order"]) == 0
    assert "added 'trie'" in capsys.readouterr().out
    assert toolbox.load(box)["entries"][-1]["name"] == "trie"
    assert toolbox_cards.main(["add", "trie2", "--property", "nope"]) == 1
    assert "unknown properties" in capsys.readouterr().err


def test_cli_without_a_command_prints_usage(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    with pytest.raises(SystemExit):
        toolbox_cards.main([])
    assert "usage" in capsys.readouterr().err
