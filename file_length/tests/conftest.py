"""Shared fixtures for the file_length tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


@pytest.fixture(autouse=True)
def _fresh_exempt_cache() -> None:
    """`load` is memoised per root; tests rewrite the file, so drop it."""
    from file_length import repo_exempt

    repo_exempt.load.cache_clear()


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway git repo that is also the cwd, as the gate expects."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def write(root: Path, relative: str, body: str) -> Path:
    """Create `relative` under `root`, parents included, and return it."""
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def lines(count: int) -> str:
    """`count` numbered lines, newline-terminated."""
    return "".join(f"line {i}\n" for i in range(count))
