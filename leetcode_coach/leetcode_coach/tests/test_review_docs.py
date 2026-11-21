"""The review text, the skill's pointers to it, and what the package ships.

The text is what Claude follows in `/leetcode review`: a command it quotes
that the CLI does not dispatch, or a cause it names that the CLI refuses,
would only show up in a live session. These tests are that check.
"""

from __future__ import annotations

from pathlib import Path
import re
import tomllib

from leetcode_coach import local_prompt, review_cli
from leetcode_coach.tests._shared import STATEMENT

PACKAGE = Path(__file__).parents[1]
DOC = PACKAGE / "DOCS-review.md"
SKILL = PACKAGE / "SKILL.md"
PYPROJECT = PACKAGE.parent / "pyproject.toml"
PREFIX = "python3 -m leetcode_coach.review_cli "
SKILL_LINE_CAP = 250


def _doc() -> str:
    return DOC.read_text(encoding="utf-8")


def test_the_text_quotes_the_three_commands_as_the_cli_takes_them() -> None:
    text = _doc()
    assert PREFIX + "review-list" in text
    assert PREFIX + "review-finish <slug> --cause <cause> [--module <unit>]" in text
    assert PREFIX + "skeleton-open <slug> <unit>" in text
    quoted = set(re.findall(re.escape(PREFIX) + r"([a-z-]+)", text))
    assert quoted == {"review-list", "review-finish", "skeleton-open"}


def test_the_text_names_every_cause_and_which_ones_make_a_card() -> None:
    text = _doc()
    for cause in review_cli.CAUSES:
        assert f"`{cause}`" in text
    assert "`missing-idea` and `idea-to-code`" in text
    assert "leetcode_coach.toolbox_cards cards" in text
    assert "make_cards.py -" in text


def test_the_text_keeps_the_rules_kuhy_set() -> None:
    text = _doc()
    for rule in (
        "nothing to review",
        "could not check",
        "at most 3 questions",
        "exactly ONE cause",
        "Never print a solution",
        "writes nothing",
        "above H1",
        "DOCS-skeletons.md",
    ):
        assert rule in text, rule


def test_skill_md_points_at_the_review_and_skeleton_texts() -> None:
    skill = SKILL.read_text(encoding="utf-8")
    assert len(skill.splitlines()) <= SKILL_LINE_CAP
    assert "DOCS-review.md" in skill
    assert "DOCS-skeletons.md" in skill
    assert "review [slug]" in skill.split("\n---\n", 1)[0]


def test_the_offline_prompt_never_hears_about_review() -> None:
    prompt = local_prompt.system_prompt(SKILL.read_text(encoding="utf-8"), STATEMENT)
    assert "DOCS-review.md" not in prompt
    assert "skeleton" not in prompt.casefold()


def test_the_package_ships_the_texts_and_the_sheets() -> None:
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    shipped = config["tool"]["setuptools"]["package-data"]["leetcode_coach"]
    assert "*.md" in shipped
    assert "skeletons/*.md" in shipped
    assert review_cli.SKELETON_DIR.name == "skeletons"
    assert review_cli.SHEET_NAME == "DOCS-{unit}.md"
