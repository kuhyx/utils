"""The installer writes the shim, hook, workflow and Commands section once."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from repo_contract import install as inst
from repo_contract import web
from repo_contract.check import violations

from .conftest import good_repo, write
from .test_web import vite_repo


def python_repo(root: Path) -> Path:
    """A python repo with tests and no contract pieces at all."""
    write(root, "pyproject.toml", "[project]\nname='x'\n")
    write(root, "tests/test_a.py", "def test_a():\n    pass\n")
    return root


def test_plan_lists_everything_for_a_bare_repo(repo: Path) -> None:
    assert inst.plan(repo) == [
        "scripts/check_repo_contract.sh",
        ".github/workflows/repo-contract.yml",
        ".pre-commit-config.yaml (repo-contract hook)",
    ]


def test_install_writes_pieces_and_is_idempotent(repo: Path) -> None:
    python_repo(repo)
    done = inst.install(repo)
    assert len(done) == 3
    shim = repo / inst.SHIM
    assert shim.stat().st_mode & stat.S_IXUSR
    assert "id: repo-contract" in (repo / inst.PRECOMMIT).read_text(encoding="utf-8")
    assert inst.install(repo) == []
    assert inst.plan(repo) == []


def test_marker_skips_workflow(repo: Path) -> None:
    write(repo, ".dep-freshness-no-workflow")
    inst.install(repo)
    assert not (repo / inst.WORKFLOW).exists()


def test_utils_itself_is_not_given_a_shim(repo: Path) -> None:
    write(repo, "repo_contract/check.py")
    assert inst.install(repo) != []
    assert not (repo / inst.SHIM).exists()


def test_hook_lands_in_the_last_local_block(repo: Path) -> None:
    write(
        repo,
        inst.PRECOMMIT.as_posix(),
        "repos:\n  - repo: local\n    hooks:\n      - id: a\n"
        "  - repo: https://example.com/x\n    hooks:\n      - id: b",
    )
    inst.install(repo)
    lines = (repo / inst.PRECOMMIT).read_text(encoding="utf-8").splitlines()
    assert lines.index("      - id: repo-contract") < lines.index(
        "  - repo: https://example.com/x"
    )


def test_hook_needs_a_local_block(repo: Path) -> None:
    write(repo, inst.PRECOMMIT.as_posix(), "repos:\n  - repo: https://example.com/x\n")
    with pytest.raises(ValueError, match="no `  - repo: local` block"):
        inst.install(repo)


def test_bootstrap_commands_creates_section_and_script(repo: Path) -> None:
    python_repo(repo)
    actions = inst.bootstrap_commands(repo)
    assert any("test_changed.sh" in a for a in actions)
    assert "## Commands" in (repo / "CLAUDE.md").read_text(encoding="utf-8")
    assert inst.bootstrap_commands(repo) == []


def test_main_check_changes_nothing(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert inst.main([str(repo), "--check"]) == 1
    out = capsys.readouterr().out
    assert "would write: scripts/check_repo_contract.sh" in out
    assert not (repo / inst.SHIM).exists()


def test_main_installs_and_passes(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    good_repo(repo)
    assert inst.main([str(repo)]) == 0
    assert "wrote: scripts/check_repo_contract.sh" in capsys.readouterr().out
    assert violations(repo)[0] == []


def test_main_no_bootstrap_leaves_violation(repo: Path) -> None:
    assert inst.main([str(repo), "--no-bootstrap"]) == 1
    assert not (repo / "CLAUDE.md").exists()


def test_main_rejects_non_repo(tmp_path: Path) -> None:
    assert inst.main([str(tmp_path)]) == 2


def test_main_reports_bootstrap_actions(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    python_repo(repo)
    inst.main([str(repo)])
    assert "bootstrap: created scripts/test_changed.sh" in capsys.readouterr().out


WEB_PIECES = [
    "repo-contract.toml ([agent_ready])",
    "scripts/check_agent_ready.sh",
    ".github/workflows/agent-ready.yml",
    ".pre-commit-config.yaml (agent-ready hook)",
]


def test_vite_repo_gets_the_agent_ready_gate(repo: Path) -> None:
    vite_repo(repo)
    assert inst.plan(repo)[3:] == WEB_PIECES
    assert inst.install(repo)[3:] == WEB_PIECES
    toml = (repo / "repo-contract.toml").read_text(encoding="utf-8")
    assert 'dist = "dist"' in toml and 'build = "pnpm run build"' in toml
    hooks = (repo / inst.PRECOMMIT).read_text(encoding="utf-8")
    assert "id: repo-contract" in hooks and "id: agent-ready" in hooks
    assert (repo / "scripts/check_agent_ready.sh").stat().st_mode & stat.S_IXUSR
    assert "check_agent_ready.sh --strict --install" in (
        repo / ".github/workflows/agent-ready.yml"
    ).read_text(encoding="utf-8")
    assert inst.install(repo) == []
    assert inst.plan(repo) == []


def test_declared_url_site_gets_gate_but_config_is_kept(repo: Path) -> None:
    body = '# mine\n[agent_ready]\nurl = "https://x.example"\n'
    write(repo, "repo-contract.toml", body)
    assert inst.install(repo)[3:] == WEB_PIECES[1:]
    assert (repo / "repo-contract.toml").read_text(encoding="utf-8") == body


def test_existing_toml_without_table_gets_it_appended(repo: Path) -> None:
    vite_repo(repo)
    write(repo, "repo-contract.toml", "[other]\nx = 1")
    inst.install(repo)
    text = (repo / "repo-contract.toml").read_text(encoding="utf-8")
    assert text.startswith("[other]\nx = 1\n") and "[agent_ready]" in text


def test_skipped_or_broken_config_installs_no_web_pieces(repo: Path) -> None:
    write(repo, "repo-contract.toml", '[agent_ready]\nskip = "auth-gated"\n')
    assert len(inst.plan(repo)) == 3
    write(repo, "repo-contract.toml", "[agent_ready]\n")
    assert len(inst.install(repo)) == 3


def test_marker_skips_agent_ready_workflow(repo: Path) -> None:
    write(repo, ".dep-freshness-no-workflow")
    write(repo, "repo-contract.toml", '[agent_ready]\nurl = "https://x.example"\n')
    inst.install(repo)
    assert not (repo / ".github/workflows/agent-ready.yml").exists()


def _agent_ready_files(repo: Path) -> list[str]:
    lines = (repo / inst.PRECOMMIT).read_text(encoding="utf-8").splitlines()
    start = lines.index("      - id: agent-ready")
    return [ln for ln in lines[start:] if ln.startswith("        files: ")]


def test_hook_carries_the_files_filter_and_follows_config(repo: Path) -> None:
    vite_repo(repo)
    inst.install(repo)
    assert _agent_ready_files(repo) == ["        files: '" + web.DEFAULT_FILES + "'"]
    with (repo / "repo-contract.toml").open("a", encoding="utf-8") as fh:
        fh.write('files = "^(app/|it\'s\\\\.html$)"\n')
    assert inst.plan(repo) == [".pre-commit-config.yaml (agent-ready hook)"]
    assert inst.install(repo) == [".pre-commit-config.yaml (agent-ready hook)"]
    assert _agent_ready_files(repo) == ["        files: '^(app/|it''s\\.html$)'"]
    assert inst.install(repo) == []


def test_hook_without_files_line_gets_one(repo: Path) -> None:
    write(repo, "repo-contract.toml", '[agent_ready]\nurl = "https://x.example"\n')
    write(
        repo,
        inst.PRECOMMIT.as_posix(),
        "repos:\n  - repo: local\n    hooks:\n      - id: agent-ready\n"
        "        entry: scripts/check_agent_ready.sh\n\n"
        "      - id: other\n        entry: x\n",
    )
    inst.install(repo)
    lines = (repo / inst.PRECOMMIT).read_text(encoding="utf-8").splitlines()
    assert lines[5].startswith("        files: '") and lines[7] == "      - id: other"
