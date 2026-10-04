"""Shared fixtures for the repo_contract tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

GOOD = """# x

## Commands

- run: n/a: library
- test: `python3 -m pytest -q`
- test-changed: `scripts/test_changed.sh`
- lint: `ruff check .`
- coverage: `python3 -m pytest -q --cov --cov-report=xml`
- coverage-gaps: `coverage-gaps coverage.xml`
"""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A throwaway git repo."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


def write(root: Path, rel: str, body: str = "x\n", mode: int | None = None) -> Path:
    """Create `rel` under `root` (parents included)."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    if mode is not None:
        path.chmod(mode)
    return path


def good_repo(root: Path) -> Path:
    """Make `root` satisfy the contract (python stack with tests)."""
    write(root, "CLAUDE.md", GOOD)
    write(root, "scripts/test_changed.sh", "#!/bin/bash\npython3 -m pytest -q\n", 0o755)
    write(root, "pyproject.toml", "[project]\nname='x'\n")
    write(root, "tests/test_a.py", "def test_a():\n    pass\n")
    return root
