"""Helpers shared by the PR import tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

from todo_hooks.tests._fakes import FakeClient
from todo_hooks.tests.conftest import git

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


def search_client(existing: str = "no tasks match") -> FakeClient:
    return FakeClient({"search_tasks": existing, "add_task": "added x"})


def pr_repo(make_repo: Callable[..., Path], n: int = 2) -> Path:
    root = make_repo("demo", origin="git@github.com:kuhyx/demo.git")
    for i in range(n):
        (root / f"g{i}").write_text("x")
        git(root, "add", f"g{i}")
        git(root, "commit", "-q", "-m", f"c{i}")
    return root
