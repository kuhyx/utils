"""dep_freshness_changed.sh: the pre-commit hook only gates manifests this branch changed.

Each test builds a throwaway git repo with a `main` branch and points the
wrapper at a stub gate (DEP_FRESHNESS_GATE) that records its arguments, so
nothing touches the network and the only thing under test is the filtering.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "dep_freshness_changed.sh"

STUB = """\
#!/bin/bash
printf '%s\\n' "$@" > "$STUB_LOG"
exit "${STUB_EXIT:-0}"
"""


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Repo on `main` with two committed manifests, then a feature branch."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    for sub in ("touched", "untouched"):
        (root / sub).mkdir()
        (root / sub / "requirements.txt").write_text("ruff==0.1.0\n")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "init")
    _git(root, "checkout", "-q", "-b", "feature")
    return root


def _run(
    repo: Path, tmp_path: Path, *files: str, **env: str
) -> tuple[int, list[str] | None]:
    stub = tmp_path / "stub.sh"
    stub.write_text(STUB)
    stub.chmod(0o755)
    log = tmp_path / "stub.log"
    log.unlink(missing_ok=True)
    full_env = {
        **os.environ,
        "DEP_FRESHNESS_GATE": str(stub),
        "STUB_LOG": str(log),
        **env,
    }
    proc = subprocess.run(
        ["bash", str(SCRIPT), *files],
        check=False,
        cwd=repo,
        env=full_env,
        capture_output=True,
        text=True,
    )
    forwarded = log.read_text().split() if log.exists() else None
    return proc.returncode, forwarded


ALL = ("touched/requirements.txt", "untouched/requirements.txt")


def test_forwards_only_uncommitted_change(repo: Path, tmp_path: Path) -> None:
    (repo / "touched" / "requirements.txt").write_text("ruff==0.2.0\n")
    assert _run(repo, tmp_path, *ALL) == (0, ["touched/requirements.txt"])


def test_forwards_committed_branch_change(repo: Path, tmp_path: Path) -> None:
    (repo / "touched" / "requirements.txt").write_text("ruff==0.2.0\n")
    _git(repo, "commit", "-q", "-am", "bump")
    assert _run(repo, tmp_path, *ALL) == (0, ["touched/requirements.txt"])


def test_forwards_untracked_manifest(repo: Path, tmp_path: Path) -> None:
    (repo / "new").mkdir()
    (repo / "new" / "requirements.txt").write_text("ruff==0.1.0\n")
    assert _run(repo, tmp_path, *ALL, "new/requirements.txt") == (
        0,
        ["new/requirements.txt"],
    )


def test_no_branch_change_skips_gate(repo: Path, tmp_path: Path) -> None:
    assert _run(repo, tmp_path, *ALL) == (0, None)


def test_gate_failure_propagates(repo: Path, tmp_path: Path) -> None:
    (repo / "touched" / "requirements.txt").write_text("ruff==0.2.0\n")
    assert _run(repo, tmp_path, *ALL, STUB_EXIT="1") == (
        1,
        ["touched/requirements.txt"],
    )


def test_unresolvable_base_fails_closed(repo: Path, tmp_path: Path) -> None:
    code, forwarded = _run(repo, tmp_path, *ALL, DEP_FRESHNESS_BASE="no-such-ref")
    assert (code, forwarded) == (0, list(ALL))


def test_subdirectory_cwd_fails_closed(repo: Path, tmp_path: Path) -> None:
    code, forwarded = _run(repo / "touched", tmp_path, "requirements.txt")
    assert (code, forwarded) == (0, ["requirements.txt"])
