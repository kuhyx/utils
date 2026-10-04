"""Bootstrap: proposals, appends, never overwriting."""

from __future__ import annotations

from pathlib import Path

import pytest

from repo_contract.bootstrap import (
    doc_path,
    insert_lines,
    main,
    missing_lines,
    script_plan,
)
from repo_contract.check import violations
from repo_contract.infer import propose

from .conftest import write


def test_insert_lines_variants() -> None:
    assert insert_lines("# t\n", []) == "# t\n"
    assert insert_lines("", ["- a: b"]) == "## Commands\n\n- a: b\n"
    assert insert_lines("# t", ["- a: b"]) == "# t\n\n## Commands\n\n- a: b\n"
    assert insert_lines("# t\n", ["- a: b"]) == "# t\n\n## Commands\n\n- a: b\n"
    assert insert_lines("# t\n\n", ["- a: b"]) == "# t\n\n## Commands\n\n- a: b\n"
    got = insert_lines("## Commands\n- run: `x`\n\n## After\ntext\n", ["- test: `y`"])
    assert got == "## Commands\n- run: `x`\n- test: `y`\n\n## After\ntext\n"
    assert insert_lines("## Commands\n- run: `x`\n", ["- t: `y`"]).endswith(
        "- t: `y`\n"
    )


def test_doc_path(repo: Path) -> None:
    assert doc_path(repo) == repo / "CLAUDE.md"
    write(repo, "AGENTS.md")
    assert doc_path(repo) == repo / "AGENTS.md"
    (repo / "CLAUDE.md").symlink_to("AGENTS.md")
    assert doc_path(repo) == (repo / "AGENTS.md").resolve()


def test_missing_lines_skips_existing(repo: Path) -> None:
    write(repo, "tests/test_a.py")
    prop = propose(repo, ["python"])
    got = missing_lines(prop, "## Commands\n- test: `mine`\n")
    assert all(not ln.startswith("- test:") for ln in got)
    assert any(ln.startswith("- lint:") for ln in got)


def test_script_plan(repo: Path) -> None:
    write(repo, "tests/test_a.py")
    prop = propose(repo, ["python"])
    assert script_plan(repo, prop) is not None
    write(repo, "scripts/test_changed.sh")
    assert script_plan(repo, prop) is None
    prop.stack = "unknown"
    (repo / "scripts/test_changed.sh").unlink()
    assert script_plan(repo, prop) is None


def test_not_a_repo(tmp_path: Path) -> None:
    assert main(["--repo", str(tmp_path)]) == 2


def test_dry_run_changes_nothing(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(repo, "pyproject.toml")
    write(repo, "tests/test_a.py")
    assert main(["--repo", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "- test: `python3 -m pytest -q`" in out
    assert not (repo / "CLAUDE.md").exists()
    assert not (repo / "scripts").exists()


def test_write_makes_repo_pass_and_is_idempotent(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(repo, "pyproject.toml", "[tool.ruff]\n")
    write(repo, "tests/test_a.py")
    write(repo, "CLAUDE.md", "# Mine\n\nKeep this.\n")
    assert main(["--repo", str(repo), "--write"]) == 0
    text = (repo / "CLAUDE.md").read_text(encoding="utf-8")
    assert text.startswith("# Mine\n\nKeep this.\n") and "## Commands" in text
    assert (repo / "scripts/test_changed.sh").stat().st_mode & 0o111
    assert violations(repo)[0] == []
    capsys.readouterr()
    assert main(["--repo", str(repo), "--write"]) == 0
    out = capsys.readouterr().out
    assert "already complete" in out and "none to create" in out
    assert (repo / "CLAUDE.md").read_text(encoding="utf-8") == text


def test_write_symlinks_claude_to_agents(repo: Path) -> None:
    write(repo, "AGENTS.md", "# a\n")
    write(repo, "pyproject.toml")
    assert main(["--repo", str(repo), "--write"]) == 0
    assert (repo / "CLAUDE.md").is_symlink()
    assert "## Commands" in (repo / "AGENTS.md").read_text(encoding="utf-8")


def test_write_new_claude_md(repo: Path) -> None:
    write(repo, "project.godot")
    assert main(["--repo", str(repo), "--write"]) == 0
    assert (repo / "CLAUDE.md").is_file()
    assert violations(repo)[0] == ["'- lint:' still holds a placeholder: <FILL IN>"]
