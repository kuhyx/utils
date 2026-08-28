"""The gate installer: three pieces in, idempotent, and no comments lost.

The point of this module is that sixteen repos get byte-identical copies, so
the assertions compare against the templates rather than against a paraphrase
of them -- a test that spelled the expected content out by hand would let the
template and the installed file drift, which is the failure the installer
exists to prevent.
"""

from __future__ import annotations

import runpy
from pathlib import Path

import pytest

from dep_freshness import install as installer
from dep_freshness.install_cli import main
from dep_freshness.tests.conftest import write

TEMPLATES = Path(installer.__file__).resolve().parent / "templates"


def _template(name: str) -> str:
    return (TEMPLATES / name).read_text(encoding="utf-8")


def test_a_bare_repo_gets_all_three_pieces(repo):
    assert installer.install(repo) == [
        "scripts/check_dependency_freshness.sh",
        ".github/workflows/dependency-freshness.yml",
        ".pre-commit-config.yaml (dependency-freshness hook)",
    ]
    delegate = repo / "scripts/check_dependency_freshness.sh"
    assert delegate.read_text(encoding="utf-8") == _template("delegate.sh")
    assert delegate.stat().st_mode & 0o111, "the hook execs it; it must be +x"
    assert (repo / ".github/workflows/dependency-freshness.yml").read_text(
        encoding="utf-8"
    ) == _template("workflow.yml")
    assert "id: dependency-freshness" in (repo / ".pre-commit-config.yaml").read_text(
        encoding="utf-8"
    )


def test_a_second_run_writes_nothing(repo):
    installer.install(repo)
    assert installer.install(repo) == []
    assert installer.plan(repo) == []


def test_plan_names_what_is_missing_without_writing_it(repo):
    assert installer.plan(repo) == [
        "scripts/check_dependency_freshness.sh",
        ".github/workflows/dependency-freshness.yml",
        ".pre-commit-config.yaml (dependency-freshness hook)",
    ]
    assert not (repo / "scripts").exists()


def test_a_drifted_copy_is_rewritten(repo):
    installer.install(repo)
    delegate = repo / "scripts/check_dependency_freshness.sh"
    delegate.write_text("#!/bin/bash\necho lol\n", encoding="utf-8")
    workflow = repo / ".github/workflows/dependency-freshness.yml"
    workflow.write_text("name: something else\n", encoding="utf-8")
    assert installer.install(repo) == [
        "scripts/check_dependency_freshness.sh",
        ".github/workflows/dependency-freshness.yml",
    ]
    assert delegate.read_text(encoding="utf-8") == _template("delegate.sh")


def test_an_existing_pre_commit_config_keeps_its_hooks_and_comments(repo):
    """Appending, not re-emitting: a YAML round-trip drops every comment.

    Each of these configs explains why its hooks exist, and that prose is the
    only record of it.
    """
    write(
        repo,
        ".pre-commit-config.yaml",
        """\
# The 250-line cap. A file that cannot be read in one piece forces re-reads.
repos:
  - repo: local
    hooks:
      - id: file-length-cap
        name: file length <= 250 lines
        entry: bash scripts/check_file_length.sh
        language: system
""",
    )
    installer.install(repo)
    body = (repo / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "# The 250-line cap." in body
    assert "id: file-length-cap" in body
    assert "id: dependency-freshness" in body


def test_a_config_that_already_has_the_hook_is_left_alone(repo):
    write(
        repo,
        ".pre-commit-config.yaml",
        """\
repos:
  - repo: local
    hooks:
      - id: dependency-freshness
        entry: scripts/check_dependency_freshness.sh
        language: system
""",
    )
    before = (repo / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    installer.install(repo)
    assert (repo / ".pre-commit-config.yaml").read_text(encoding="utf-8") == before


def test_a_config_without_a_trailing_newline_still_appends_cleanly(repo):
    write(repo, ".pre-commit-config.yaml", "repos:\n  - repo: local\n    hooks:")
    installer.install(repo)
    body = (repo / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert body.startswith("repos:\n  - repo: local\n    hooks:\n\n      #")
    assert "id: dependency-freshness" in body


def test_fvmrc_is_only_for_repos_that_hold_a_pubspec(repo):
    assert installer.write_fvmrc(repo, "3.47.2") is False
    assert not (repo / ".fvmrc").exists()
    write(repo, "app/pubspec.yaml", "name: demo\n")
    assert installer.write_fvmrc(repo, "3.47.2") is True
    assert (repo / ".fvmrc").read_text(
        encoding="utf-8"
    ) == '{\n  "flutter": "3.47.2"\n}\n'
    assert installer.write_fvmrc(repo, "3.47.2") is False


def test_the_cli_installs_and_reports_each_piece(repo, capsys):
    assert main([str(repo)]) == 0
    out = capsys.readouterr().out
    assert "wrote: scripts/check_dependency_freshness.sh" in out
    assert "wrote: .github/workflows/dependency-freshness.yml" in out


def test_the_cli_check_mode_writes_nothing(repo, capsys):
    assert main([str(repo), "--check"]) == 0
    assert (
        "would write: scripts/check_dependency_freshness.sh" in capsys.readouterr().out
    )
    assert not (repo / "scripts").exists()
    main([str(repo)])
    assert main([str(repo), "--check"]) == 0
    assert "gate already current" in capsys.readouterr().out


def test_the_cli_pins_the_sdk_when_asked(repo, monkeypatch, capsys):
    monkeypatch.setattr(
        "dep_freshness.install_cli.flutter_latest", lambda: ("3.47.2", "3.13.2")
    )
    write(repo, "pubspec.yaml", "name: demo\n")
    assert main([str(repo), "--fvm"]) == 0
    assert "wrote: .fvmrc (flutter 3.47.2)" in capsys.readouterr().out
    # Same version again: the pin is already right, so nothing is reported.
    assert main([str(repo), "--fvm"]) == 0
    assert ".fvmrc" not in capsys.readouterr().out


def test_an_unresolvable_sdk_leaves_the_pin_alone(repo, monkeypatch, capsys):
    """Offline, the alternative is pinning every repo to a guessed number."""
    monkeypatch.setattr(
        "dep_freshness.install_cli.flutter_latest", lambda: (None, None)
    )
    write(repo, "pubspec.yaml", "name: demo\n")
    assert main([str(repo), "--fvm"]) == 1
    assert "could not resolve latest stable Flutter" in capsys.readouterr().err
    assert not (repo / ".fvmrc").exists()


def test_the_module_entrypoint_runs_the_cli(repo, monkeypatch):
    monkeypatch.setattr("sys.argv", ["install_main", str(repo), "--check"])
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("dep_freshness.install_main", run_name="__main__")
    assert exit_info.value.code == 0
