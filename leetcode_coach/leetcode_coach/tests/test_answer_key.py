"""Tests for the answer key (TODO-coach-ui.md decision 5).

The key is grader-internal: nothing in it is displayed. Even so, the design
rule and the post-mortem points are what the grader's feedback is built from,
and that feedback goes through the same leak check as coach replies, so they
must name no toolbox entry themselves.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from leetcode_coach import answer_key, leak, progress, toolbox

if TYPE_CHECKING:
    from pathlib import Path

BOX = toolbox.load_safe()
KEY = answer_key.load_answers()


def _slugs() -> list[str]:
    return [p["slug"] for ps in progress.load_clusters().values() for p in ps]


def test_every_cluster_problem_has_exactly_one_answer() -> None:
    slugs = _slugs()
    assert len(slugs) == 24
    assert set(KEY) == set(slugs)
    assert list(answer_key.load()["problems"]) == slugs


def test_every_entry_name_exists_in_the_toolbox() -> None:
    names = {e.name for e in BOX.entries}
    for slug, answer in KEY.items():
        assert set(answer.entries) <= names, slug
        assert set(answer.also_accepted) <= names, slug
        assert not set(answer.entries) & set(answer.also_accepted), slug


def test_every_key_requirement_is_in_the_property_vocabulary() -> None:
    for slug, answer in KEY.items():
        assert set(answer.key_requirements) <= set(BOX.properties), slug


def test_the_correct_entries_have_every_key_requirement() -> None:
    by_name = {e.name: set(e.properties) for e in BOX.entries}
    for slug, answer in KEY.items():
        have = set().union(*(by_name[n] for n in answer.entries))
        assert set(answer.key_requirements) <= have, slug


def test_sizes_are_within_the_agreed_bounds() -> None:
    for slug, answer in KEY.items():
        assert 1 <= len(answer.entries) <= 3, slug
        assert 2 <= len(answer.key_requirements) <= 5, slug
        assert 2 <= len(answer.postmortem_points) <= 4, slug
        assert len(set(answer.key_requirements)) == len(answer.key_requirements), slug
        assert answer.design_rule.strip(), slug
        assert all(p.strip() for p in answer.postmortem_points), slug


def test_design_rule_and_postmortem_points_name_no_entry() -> None:
    for slug, answer in KEY.items():
        for text in (answer.design_rule, *answer.postmortem_points):
            assert leak.leaked_names(text, [], BOX) == [], (slug, text)


def test_the_leak_check_would_catch_a_naming_point() -> None:
    # Guards the test above: a green run must mean "checked", not "skipped".
    assert leak.leaked_names("Pick a hash map.", [], BOX) == ["hash map"]


def _write(tmp_path: Path, problems: Any) -> Path:
    path = tmp_path / "key.json"
    path.write_text(json.dumps({"problems": problems}), encoding="utf-8")
    return path


GOOD: dict[str, Any] = {
    "design_rule": "r",
    "entries": ["XOR"],
    "also_accepted": [],
    "key_requirements": ["invertible", "commutative"],
    "postmortem_points": ["a", "b"],
}


def test_load_answers_reads_a_well_formed_file(tmp_path: Path) -> None:
    got = answer_key.load_answers(_write(tmp_path, {"s": GOOD}))
    assert got["s"].entries == ("XOR",)
    assert got["s"].design_rule == "r"


def test_load_defaults_to_the_shipped_file() -> None:
    assert answer_key.load() == json.loads(
        answer_key.ANSWER_KEY_PATH.read_text(encoding="utf-8")
    )


@pytest.mark.parametrize(
    "problems",
    [
        [],
        {"s": []},
        {"s": {**GOOD, "design_rule": 3}},
        {"s": {**GOOD, "entries": "XOR"}},
        {"s": {**GOOD, "key_requirements": [1]}},
        {"s": {k: v for k, v in GOOD.items() if k != "postmortem_points"}},
    ],
)
def test_load_answers_rejects_a_malformed_file(tmp_path: Path, problems: Any) -> None:
    with pytest.raises(TypeError):
        answer_key.load_answers(_write(tmp_path, problems))


def test_also_accepted_is_optional(tmp_path: Path) -> None:
    bare = {k: v for k, v in GOOD.items() if k != "also_accepted"}
    got = answer_key.load_answers(_write(tmp_path, {"s": bare}))
    assert got["s"].also_accepted == ()
