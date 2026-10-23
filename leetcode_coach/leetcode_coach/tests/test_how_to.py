"""`how_to` is the one source of the commands and method the status app shows.

SKILL.md quotes it, the Coach tab renders it, and these tests are what stop
the two copies from drifting apart (the reason it is one module).
"""

from __future__ import annotations

from pathlib import Path
import re

from leetcode_coach import cluster_cli, how_to, report

DOC = Path(__file__).parents[1] / "DOCS-how-to.md"
SKILL = Path(__file__).parents[1] / "SKILL.md"


def test_block_is_commands_steps_note_and_the_first_command() -> None:
    block = how_to.block("two-pointers")

    assert block["first_command"] == "leetcode --cluster two-pointers"
    assert len(block["commands"]) == 4
    assert len(block["steps"]) == 4
    assert block["next_note"] == how_to.NEXT_NOTE
    assert all(c["command"] and c["meaning"] for c in block["commands"])
    assert all(s["name"] and s["text"] for s in block["steps"])


def test_no_first_cluster_means_no_first_command() -> None:
    assert how_to.block(None)["first_command"] is None


def test_command_templates() -> None:
    assert how_to.cluster_command("intervals") == "leetcode --cluster intervals"
    assert how_to.retest_command("3sum") == "leetcode --retest 3sum"


def test_every_listed_command_is_one_the_launcher_dispatches() -> None:
    known = {*cluster_cli.COMMANDS, report.COMMAND}
    for entry in how_to.COMMANDS:
        word = entry.command.split()[1]
        assert word in known or word == "<url>", entry.command


def test_the_doc_quotes_every_command_and_step_verbatim() -> None:
    skill = DOC.read_text(encoding="utf-8")

    for entry in how_to.COMMANDS:
        assert f"`{entry.command}` - {entry.meaning}" in skill
    for number, step in enumerate(how_to.STEPS, start=1):
        assert f"{number}. **{step.name}** - {step.text}" in skill
    assert how_to.NEXT_NOTE in skill


def test_skill_md_points_at_the_doc() -> None:
    assert "DOCS-how-to.md" in SKILL.read_text(encoding="utf-8")


def test_the_method_never_names_a_toolbox_operation() -> None:
    # The Stop hook bounces a reply that names one before kuhy's first code;
    # the same words on the Coach tab would teach kuhy to skip the search.
    text = " ".join(s.text.casefold() for s in how_to.STEPS)

    assert re.search(r"\b(xor|hash map|sort|stack|two pointers)\b", text) is None
