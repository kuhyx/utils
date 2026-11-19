# Copyright (c) 2026 Krzysztof Rudnicki
"""Origin lookup: every remote URL form, and every way a checkout has none."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest

from feedback_inbox import _origin
from feedback_inbox._origin import origin_slug, repo_slug, slug_from_url
from feedback_inbox.tests.test_support import make_checkout

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/Sepci0/cleanup-plate",
        "https://github.com/Sepci0/cleanup-plate.git",
        "https://github.com/Sepci0/cleanup-plate/\n",
        "https://kuhy@github.com/Sepci0/cleanup-plate.git",
        "git@github.com:Sepci0/cleanup-plate.git",
        "ssh://git@github.com/Sepci0/cleanup-plate",
        "ssh://git@github.com:22/Sepci0/cleanup-plate.git",
    ],
)
def test_github_urls_give_the_slug(url: str) -> None:
    assert slug_from_url(url) == "Sepci0/cleanup-plate"


@pytest.mark.parametrize(
    "url",
    [
        "/home/someone/mirror/cleanup-plate",
        "file:///srv/git/cleanup-plate.git",
        "https://gitea.example.org/Sepci0/cleanup-plate.git",
        "https://github.com/Sepci0",
        "https://github.com/Sepci0/cleanup-plate/extra",
        "",
    ],
)
def test_other_urls_give_none(url: str) -> None:
    assert slug_from_url(url) is None


def test_checkout_origin_is_read(tmp_path: Path) -> None:
    repo = make_checkout(tmp_path / "todo", "https://github.com/kuhyx/todo-app.git")
    assert origin_slug(repo) == "kuhyx/todo-app"


def test_no_checkout_or_no_origin_is_none(tmp_path: Path) -> None:
    (tmp_path / "plain").mkdir()
    assert origin_slug(tmp_path / "missing") is None
    assert origin_slug(tmp_path / "plain") is None
    assert origin_slug(make_checkout(tmp_path / "bare", None)) is None


def test_missing_or_hung_git_is_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_checkout(tmp_path / "todo", "https://github.com/kuhyx/todo-app")

    def hang(*args: object, **kwargs: object) -> None:
        msg = "git"
        raise subprocess.TimeoutExpired(msg, _origin.GIT_TIMEOUT)

    monkeypatch.setattr(_origin.subprocess, "run", hang)
    assert origin_slug(repo) is None
    monkeypatch.setattr(_origin.shutil, "which", lambda _: None)
    assert origin_slug(repo) is None


def test_repo_slug_falls_back_to_the_owner_guess(tmp_path: Path) -> None:
    make_checkout(tmp_path / "todo", "git@github.com:kuhyx/todo-app.git")
    assert repo_slug(tmp_path, "todo", "kuhyx") == "kuhyx/todo-app"
    assert repo_slug(tmp_path, "museum", "kuhyx") == "kuhyx/museum"
