"""The gate end to end."""

from __future__ import annotations

from pathlib import Path

import pytest

from repo_contract.check import Unreadable, main, read_doc, violations

from .conftest import GOOD, good_repo, write


def problems(repo: Path) -> list[str]:
    return violations(repo)[0]


def test_good_repo_passes(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    good_repo(repo)
    assert main(["--repo", str(repo)]) == 0
    assert capsys.readouterr().err == ""


def test_exit_2_when_not_repo(tmp_path: Path) -> None:
    assert main(["--repo", str(tmp_path)]) == 2
    assert main(["--repo", str(tmp_path / "nope")]) == 2


def test_exit_2_when_doc_unreadable(repo: Path) -> None:
    write(repo, "CLAUDE.md").write_bytes(b"\xff\xfe\x00bad")
    assert main(["--repo", str(repo)]) == 2
    with pytest.raises(Unreadable):
        read_doc(repo)


def test_exit_1_prints_each(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--repo", str(repo)]) == 1
    assert "CLAUDE.md missing" in capsys.readouterr().err


def test_missing_doc_variants(repo: Path) -> None:
    assert "or AGENTS.md" in problems(repo)[0]
    write(repo, "AGENTS.md", GOOD)
    assert "symlink it to AGENTS.md" in problems(repo)[0]
    (repo / "CLAUDE.md").symlink_to("nowhere.md")
    assert "dangling" in problems(repo)[0]


def test_symlinked_agents_passes(repo: Path) -> None:
    good_repo(repo)
    (repo / "AGENTS.md").write_text(GOOD, encoding="utf-8")
    (repo / "CLAUDE.md").unlink()
    (repo / "CLAUDE.md").symlink_to("AGENTS.md")
    assert problems(repo) == []


def test_no_section_and_missing_keys(repo: Path) -> None:
    write(repo, "CLAUDE.md", "# x\n")
    assert "no '## Commands'" in problems(repo)[0]
    write(repo, "CLAUDE.md", "## Commands\n- test: `pytest -q`\n")
    assert "missing: - run:, - test-changed:" in problems(repo)[0]


def test_script_rules(repo: Path) -> None:
    good_repo(repo)
    (repo / "scripts/test_changed.sh").chmod(0o644)
    assert "not executable" in problems(repo)[0]
    write(repo, "scripts/test_changed.sh", "pytest -v\n", 0o755)
    assert "verbosely" in problems(repo)[0]
    (repo / "scripts/test_changed.sh").unlink()
    assert "existing changed-files script" in problems(repo)[0]
    write(repo, "scripts/test_changed.sh").write_bytes(b"\xff\xfe")
    (repo / "scripts/test_changed.sh").chmod(0o755)
    with pytest.raises(Unreadable):
        violations(repo)


def test_na_test_with_real_tests_fails(repo: Path) -> None:
    good_repo(repo)
    body = GOOD.replace("`python3 -m pytest -q`", "n/a: none", 1)
    write(repo, "CLAUDE.md", body)
    out = problems(repo)
    assert any("n/a but the repo contains tests" in p for p in out)
    assert any("must be n/a when test is n/a" in p for p in out)


def test_godot_without_tests_may_be_na(repo: Path) -> None:
    na = "n/a: no tests"
    body = "## Commands\n- run: `godot --path .`\n" + "".join(
        f"- {k}: {na}\n"
        for k in ("test", "test-changed", "lint", "coverage", "coverage-gaps")
    )
    write(repo, "CLAUDE.md", body)
    write(repo, "project.godot")
    assert problems(repo) == []


def test_real_test_cannot_have_na_chain(repo: Path) -> None:
    good_repo(repo)
    body = GOOD.replace("`scripts/test_changed.sh`", "n/a: why")
    body = body.replace("`coverage-gaps coverage.xml`", "n/a: why")
    write(repo, "CLAUDE.md", body)
    out = problems(repo)
    assert any("test-changed:' cannot be n/a" in p for p in out)
    assert any("must run the shared lister" in p for p in out)


def test_wrong_lister_and_coverage_na_ok(repo: Path) -> None:
    good_repo(repo)
    write(
        repo,
        "CLAUDE.md",
        GOOD.replace("`coverage-gaps coverage.xml`", "`cat coverage.xml`"),
    )
    assert any("must start with `coverage-gaps" in p for p in problems(repo))
    body = GOOD.replace("`python3 -m pytest -q --cov --cov-report=xml`", "n/a: no cov")
    write(
        repo, "CLAUDE.md", body.replace("`coverage-gaps coverage.xml`", "n/a: no cov")
    )
    assert problems(repo) == []


def test_verbose_and_placeholder_reported(repo: Path) -> None:
    good_repo(repo)
    write(
        repo,
        "CLAUDE.md",
        GOOD.replace("pytest -q`", "pytest -v`", 1).replace(
            "ruff check .", "<FILL IN>"
        ),
    )
    out = problems(repo)
    assert any("quiet by default" in p for p in out)
    assert any("placeholder" in p for p in out)
