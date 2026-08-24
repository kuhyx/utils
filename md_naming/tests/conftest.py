"""Shared fixtures for the md_naming tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A throwaway git repo, so git-ignore lookups behave as in real use."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


def write(root: Path, relative: str, body: str = "# x\n") -> Path:
    """Create `relative` under `root`, parents included, and return it."""
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path
