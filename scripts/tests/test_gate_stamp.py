"""gate_stamp.sh step / full --list: the heavy gate split into <60 s calls.

Each test builds a throwaway git repo whose manual-stage hooks are
`language: system` with `entry: true` / `entry: false`, so pre-commit runs
offline in well under a second and the only thing under test is the stamp
bookkeeping. Every hook is `always_run` -- a hook with no matching files is
"Skipped" with exit 0, which would let `entry: false` pass.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "gate_stamp.sh"

CONFIG = """\
default_stages: [pre-commit]
repos:
  - repo: local
    hooks:
      - id: ok-a
        name: ok a
        entry: "true"
        language: system
        pass_filenames: false
        always_run: true
        stages: [manual]
      - id: ok-b
        name: ok b
        entry: "true"
        language: system
        pass_filenames: false
        always_run: true
        stages: [pre-push, manual]
      - id: bad
        name: bad
        entry: "false"
        language: system
        pass_filenames: false
        always_run: true
        stages: [manual]
      - id: commit-only
        name: commit only
        entry: "true"
        language: system
        pass_filenames: false
        always_run: true
"""


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _gate(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )


def _make_repo(path: Path, config: str) -> Path:
    path.mkdir()
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.name", "t")
    _git(path, "config", "user.email", "t@example.invalid")
    (path / ".pre-commit-config.yaml").write_text(config, encoding="utf-8")
    (path / "f.txt").write_text("x\n", encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-q", "-m", "init")
    return path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return _make_repo(tmp_path / "r", CONFIG)


def _git_dir(repo: Path) -> Path:
    return (repo / _git(repo, "rev-parse", "--git-dir")).resolve()


def _tree(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD^{tree}")


def test_full_list_prints_manual_ids_only(repo: Path) -> None:
    res = _gate(repo, "full", "--list")
    assert res.returncode == 0, res.stderr
    assert res.stdout.splitlines() == ["ok-a", "ok-b", "bad"]


def test_list_counts_unstaged_hooks_when_default_stages_is_absent(
    tmp_path: Path,
) -> None:
    # pre-commit treats a missing default_stages as "every stage", so a hook
    # without `stages` runs under --hook-stage manual and must be a step too.
    config = CONFIG.replace("default_stages: [pre-commit]\n", "")
    r = _make_repo(tmp_path / "nodefault", config)
    res = _gate(r, "full", "--list")
    assert res.stdout.splitlines() == ["ok-a", "ok-b", "bad", "commit-only"]


def test_list_counts_unstaged_hooks_when_default_stages_has_manual(
    tmp_path: Path,
) -> None:
    config = CONFIG.replace("[pre-commit]", "[pre-commit, manual]")
    r = _make_repo(tmp_path / "withmanual", config)
    res = _gate(r, "full", "--list")
    assert "commit-only" in res.stdout.splitlines()


def test_step_records_and_reports_missing_ids(repo: Path) -> None:
    res = _gate(repo, "step", "ok-a")
    assert res.returncode == 0, res.stdout + res.stderr
    steps = (_git_dir(repo) / "gate-steps").read_text(encoding="utf-8")
    assert f"{_tree(repo)} ok-a" in steps.splitlines()
    assert "ok-b" in res.stdout
    assert "bad" in res.stdout
    assert not (_git_dir(repo) / "gate-stamp").exists()


def test_rerunning_a_step_does_not_duplicate_its_record(repo: Path) -> None:
    _gate(repo, "step", "ok-a")
    _gate(repo, "step", "ok-a")
    steps = (_git_dir(repo) / "gate-steps").read_text(encoding="utf-8")
    assert steps.splitlines().count(f"{_tree(repo)} ok-a") == 1


def test_a_failing_step_records_nothing(repo: Path) -> None:
    res = _gate(repo, "step", "bad")
    assert res.returncode != 0
    steps = _git_dir(repo) / "gate-steps"
    assert not steps.exists() or "bad" not in steps.read_text(encoding="utf-8")
    assert not (_git_dir(repo) / "gate-stamp").exists()


def test_stamp_appears_only_after_every_manual_id_passes(tmp_path: Path) -> None:
    config = CONFIG.replace('entry: "false"', 'entry: "true"')
    r = _make_repo(tmp_path / "allgreen", config)
    stamp = _git_dir(r) / "gate-stamp"
    for hook in ("ok-a", "ok-b"):
        assert _gate(r, "step", hook).returncode == 0
        assert not stamp.exists()
    res = _gate(r, "step", "bad")
    assert res.returncode == 0, res.stdout + res.stderr
    assert stamp.read_text(encoding="utf-8").split()[0] == _tree(r)
    assert "recorded tree" in res.stdout
    assert _gate(r, "check").returncode == 0


def test_step_on_a_dirty_tree_is_refused(repo: Path) -> None:
    (repo / "f.txt").write_text("changed\n", encoding="utf-8")
    res = _gate(repo, "step", "ok-a")
    assert res.returncode == 2
    assert "differs from HEAD" in res.stderr
    assert not (_git_dir(repo) / "gate-steps").exists()


def test_step_with_an_unknown_id_is_refused(repo: Path) -> None:
    for hook in ("nope", "commit-only"):
        res = _gate(repo, "step", hook)
        assert res.returncode == 2
        assert "not a manual-stage hook" in res.stderr
    assert not (_git_dir(repo) / "gate-steps").exists()


def test_step_without_an_id_is_refused(repo: Path) -> None:
    res = _gate(repo, "step")
    assert res.returncode == 2


def test_step_in_a_linked_worktree_uses_its_own_git_dir(repo: Path) -> None:
    wt = repo.parent / "wt"
    _git(repo, "worktree", "add", "-q", str(wt))
    res = _gate(wt, "step", "ok-a")
    assert res.returncode == 0, res.stdout + res.stderr
    assert (repo / ".git/worktrees/wt/gate-steps").exists()
    assert not (repo / ".git/gate-steps").exists()


def test_full_hints_at_step(repo: Path) -> None:
    res = _gate(repo, "full")
    assert "step" in res.stdout.splitlines()[0]
    assert res.returncode != 0  # `bad` fails, so no stamp
    assert not (_git_dir(repo) / "gate-stamp").exists()


def test_check_failure_mentions_list_and_step(repo: Path) -> None:
    res = _gate(repo, "check")
    assert res.returncode == 1
    assert "full --list" in res.stderr
    assert "step <id>" in res.stderr
