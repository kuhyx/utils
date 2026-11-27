"""Throwaway git repos with pinned dates, under a redirected HOME/git config.

Every test that runs git goes through `isolated_git`, so neither the real
~/.gitconfig nor any hook from it can leak in, and dates are explicit so the
window maths is deterministic.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

ME = "krzysztofrudnicki0@gmail.com"
DAY = 86_400
# 2026-11-18 12:00 UTC: far from midnight in any timezone the tests run in.
NOW = 1_795_003_200


@pytest.fixture(autouse=True)
def isolated_git(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point HOME and the global git config at an empty scratch dir."""
    home = tmp_path_factory.mktemp("home")
    cfg = home / "gitconfig"
    cfg.write_text("[user]\n\tname = T\n\temail = t@example.com\n[init]\n\tdefaultBranch = main\n")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(cfg))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("TZ", "UTC")


def run(cwd: Path, *args: str, env: dict[str, str] | None = None) -> str:
    """Run git in `cwd` and return stdout."""
    full = {**os.environ, **(env or {})}
    return subprocess.run(
        ["git", *args], cwd=cwd, env=full, check=True, capture_output=True, text=True
    ).stdout.strip()


@dataclass
class Repo:
    """A scratch repository with helpers that pin author/committer dates."""

    path: Path

    def _env(self, ts: int, email: str) -> dict[str, str]:
        date = f"@{ts} +0000"
        return {
            "GIT_AUTHOR_DATE": date,
            "GIT_COMMITTER_DATE": date,
            "GIT_AUTHOR_EMAIL": email,
            "GIT_COMMITTER_EMAIL": email,
            "GIT_AUTHOR_NAME": "A",
            "GIT_COMMITTER_NAME": "A",
        }

    def commit(self, files: dict[str, str | bytes | None], ts: int, email: str = ME) -> str:
        """Write/delete `files` (None deletes) and commit them at `ts`."""
        for name, content in files.items():
            target = self.path / name
            if content is None:
                run(self.path, "rm", "-q", name)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                target.write_bytes(content)
            else:
                target.write_text(content)
            run(self.path, "add", name)
        run(self.path, "commit", "-q", "--allow-empty", "-m", "c", env=self._env(ts, email))
        return run(self.path, "rev-parse", "HEAD")

    def rename(self, old: str, new: str, ts: int, extra: str = "") -> str:
        """`git mv old new`, optionally appending a line, committed at `ts`."""
        run(self.path, "mv", old, new)
        if extra:
            with (self.path / new).open("a") as fh:
                fh.write(extra)
            run(self.path, "add", new)
        run(self.path, "commit", "-q", "-m", "mv", env=self._env(ts, ME))
        return run(self.path, "rev-parse", "HEAD")

    def tag(self, name: str, ts: int, annotated: bool = False) -> None:
        """Create a lightweight or annotated tag dated `ts`."""
        args = ["tag", "-a", "-m", name, name] if annotated else ["tag", name]
        run(self.path, *args, env=self._env(ts, ME))


def lines(n: int, prefix: str = "x") -> str:
    """`n` distinct lines of text."""
    return "".join(f"{prefix}{i}\n" for i in range(n))


@pytest.fixture
def make_repo(tmp_path: Path):
    """Factory: `make_repo("name", branch="main")` -> initialised Repo."""

    def _make(name: str, branch: str = "main", root: Path | None = None) -> Repo:
        path = (root or tmp_path / "src") / name
        path.mkdir(parents=True)
        run(path, "init", "-q", "-b", branch)
        return Repo(path)

    return _make
