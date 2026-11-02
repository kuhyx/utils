"""Shared fixtures: fake MCP server, temp git repos, tmp-rooted Paths."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from todo_hooks.context import Context
from todo_hooks.paths import Paths
from todo_hooks.tests._fakes import FakeMcp

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

_GIT_ENV = ["-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]


@pytest.fixture
def mcp() -> Iterator[FakeMcp]:
    """A running fake MCP server on an ephemeral port."""
    server = FakeMcp().start()
    yield server
    server.stop()


@pytest.fixture
def paths(tmp_path: Path) -> Paths:
    """Every path rooted in tmp_path, never in the real home."""
    return Paths(
        token_file=tmp_path / "cfg" / "client-token",
        trust_file=tmp_path / "cfg" / "trusted-checks",
        report_file=tmp_path / "state" / "report.txt",
        src_root=tmp_path / "src",
        capped=None,
    )


def git(cwd: Path, *args: str) -> str:
    """Run git in `cwd` with a fixed identity and return stdout."""
    done = subprocess.run(
        ["git", *_GIT_ENV, *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return done.stdout.strip()


@pytest.fixture
def make_repo(tmp_path: Path) -> Callable[..., Path]:
    """Factory: init a repo with an optional origin URL and one commit."""

    def _make(
        name: str = "demo",
        *,
        origin: str | None = None,
        message: str = "init",
        parent: Path | None = None,
    ) -> Path:
        root = (parent or tmp_path / "repos") / name
        root.mkdir(parents=True)
        git(root, "init", "-q", "-b", "main")
        if origin:
            git(root, "remote", "add", "origin", origin)
        (root / "f.txt").write_text("x")
        git(root, "add", "f.txt")
        git(root, "commit", "-q", "-m", message)
        return root

    return _make


@pytest.fixture
def make_ctx(paths: Paths) -> Callable[..., tuple[Context, list[str]]]:
    """Factory: a Context around a fake client, with captured output lines."""

    def _make(
        client: object,
        cwd: Path,
        env: dict[str, str] | None = None,
    ) -> tuple[Context, list[str]]:
        lines: list[str] = []
        ctx = Context(
            env=env or {},
            cwd=cwd,
            paths=paths,
            make_client=lambda: client,  # type: ignore[arg-type,return-value]
            out=lines.append,
        )
        return ctx, lines

    return _make
