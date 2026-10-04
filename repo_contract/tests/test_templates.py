"""Run the generated test_changed.sh scripts against real throwaway repos."""

from __future__ import annotations

import subprocess
from pathlib import Path

from repo_contract.bootstrap import TEMPLATES

from .conftest import write


def run(
    repo: Path, stack: str, *, env_path: str | None = None
) -> subprocess.CompletedProcess[str]:
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "commit",
            "-qm",
            "i",
        ],
        check=True,
    )
    return subprocess.run(
        ["bash", str(TEMPLATES / f"{stack}.sh")],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )


def test_python_runs_only_mapped_tests(repo: Path) -> None:
    write(repo, "pkg/a.py", "x = 1\n")
    write(repo, "tests/test_a.py", "def test_a():\n    assert True\n")
    write(repo, "tests/test_b.py", "def test_b():\n    assert False\n")
    done = run(repo, "python")
    assert "nothing to test" in done.stdout and done.returncode == 0
    write(repo, "pkg/a.py", "x = 2\n")
    done = subprocess.run(
        ["bash", str(TEMPLATES / "python.sh")],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0 and "1 passed" in done.stdout
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "commit",
            "-qm",
            "2",
        ],
        check=True,
    )
    write(repo, "pkg/c.py", "y = 1\n")
    done = subprocess.run(
        ["bash", str(TEMPLATES / "python.sh")],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert "full suite" in done.stdout and done.returncode != 0


def test_python_ignores_non_python_changes(repo: Path) -> None:
    write(repo, "README.md")
    run(repo, "python")
    write(repo, "README.md", "changed\n")
    done = subprocess.run(
        ["bash", str(TEMPLATES / "python.sh")],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert "no python changes" in done.stdout


def test_shell_template(repo: Path) -> None:
    write(repo, "scripts/a.sh", "echo a\n")
    write(repo, "tests/test_a.sh", "exit 0\n")
    run(repo, "shell")
    write(repo, "scripts/a.sh", "echo b\n")
    done = subprocess.run(
        ["bash", str(TEMPLATES / "shell.sh")],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0 and "pass" in done.stdout
