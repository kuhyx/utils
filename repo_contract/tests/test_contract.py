"""Parser and entry validation."""

from __future__ import annotations

from pathlib import Path

from repo_contract.contract import (
    Entry,
    commands_section,
    entry_problems,
    has_section,
    is_verbose,
    parse_entries,
    script_token,
    verbose_in_script,
)

from .conftest import GOOD, write


def test_section_extraction_respects_fences_and_next_heading() -> None:
    text = "# t\n## Commands\n- a: b\n```\n## Other\n```\n## Next\n- c: d\n"
    assert commands_section(text) == ["- a: b", "```", "## Other", "```"]
    assert has_section(text)
    assert not has_section("```\n## Commands\n```\n")
    assert not has_section("## Commandsx\n")


def test_parse_good() -> None:
    entries, problems = parse_entries(GOOD)
    assert not problems
    assert entries["run"] == Entry("run", None, "library")
    assert entries["test"].command == "python3 -m pytest -q"


def test_parse_na_forms_and_errors() -> None:
    text = (
        "## Commands\n- run: n/a (a game)\n- test: n/a\n- lint: n/a:   \n"
        "- coverage: plain words\n- test: `x`\n- lint: `a`\n- lint: `b`\n- other: `z`\nprose\n"
    )
    entries, problems = parse_entries(text)
    assert entries["run"].na_reason == "a game"
    assert any("must carry a reason" in p for p in problems)
    assert any("needs a backticked command" in p for p in problems)
    assert any("duplicate '- lint:'" in p for p in problems)
    assert "other" not in entries


def test_verbosity() -> None:
    assert is_verbose("pytest -v")
    assert is_verbose("pytest -vv x")
    assert is_verbose("tool --verbose")
    assert is_verbose("flutter test --reporter expanded")
    assert not is_verbose("pytest -q")
    assert is_verbose("echo 'unterminated -v")
    assert not verbose_in_script("# pytest -v\ngrep -v x\npytest -q\n")
    assert verbose_in_script("python3 -m pytest -v\n")


def test_entry_problems() -> None:
    assert entry_problems(Entry("run", None, "lib")) == []
    assert entry_problems(Entry("test", "pytest -q", None)) == []
    assert entry_problems(Entry("run", "go run -v .", None)) == []
    assert len(entry_problems(Entry("test", "pytest -v", None))) == 1
    assert "placeholder" in entry_problems(Entry("lint", "<FILL IN>", None))[0]


def test_script_token(tmp_path: Path) -> None:
    write(tmp_path, "scripts/t.sh")
    assert script_token("bash scripts/t.sh", tmp_path) == tmp_path / "scripts/t.sh"
    assert script_token("scripts/missing.sh", tmp_path) is None
    assert script_token("pytest -q", tmp_path) is None
    assert script_token("echo 'bad scripts/t.sh", tmp_path) == tmp_path / "scripts/t.sh"
