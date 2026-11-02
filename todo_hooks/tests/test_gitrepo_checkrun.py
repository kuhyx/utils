"""Tests for git helpers and the done_check runner."""

from __future__ import annotations

import stat
import time
from typing import TYPE_CHECKING

import pytest

from todo_hooks.checkrun import CHECK_TIMEOUT, run_check
from todo_hooks.gitrepo import (
    expected_repo,
    head_sha,
    head_todo_ids,
    origin_slug,
    parse_slug,
    repo_name,
    toplevel,
)
from todo_hooks.tests.conftest import git

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


@pytest.mark.parametrize(
    ("url", "slug"),
    [
        ("git@github.com:kuhyx/utils.git", ("kuhyx", "utils")),
        ("https://github.com/kuhyx/utils", ("kuhyx", "utils")),
        ("https://github.com/kuhyx/utils.git/", ("kuhyx", "utils")),
        ("ssh://git@github.com/kuhyx/utils.git", ("kuhyx", "utils")),
        ("https://user:tok@github.com/o/n.git", ("o", "n")),
        ("/srv/git/local.git", None),
        ("nonsense", None),
        ("", None),
    ],
)
def test_parse_slug(url: str, slug: tuple[str, str] | None) -> None:
    assert parse_slug(url) == slug


def test_toplevel_and_non_repo(make_repo: Callable[..., Path], tmp_path: Path) -> None:
    root = make_repo()
    (root / "sub").mkdir()
    assert toplevel(root / "sub") == root.resolve()
    assert toplevel(tmp_path / "nowhere-at-all") is None
    plain = tmp_path / "plain"
    plain.mkdir()
    assert toplevel(plain) is None


def test_repo_name_from_origin_else_basename(make_repo: Callable[..., Path]) -> None:
    with_origin = make_repo("dirname", origin="git@github.com:kuhyx/real-name.git")
    assert repo_name(with_origin) == "real-name"
    assert origin_slug(with_origin) == ("kuhyx", "real-name")
    assert expected_repo(with_origin) == "kuhyx/real-name"
    bare = make_repo("solo")
    assert origin_slug(bare) is None
    assert repo_name(bare) == "solo"
    assert expected_repo(bare) == "kuhyx/solo"
    odd = make_repo("odd", origin="/srv/odd.git")
    assert repo_name(odd) == "odd"


def test_head_sha_is_short(make_repo: Callable[..., Path]) -> None:
    root = make_repo()
    assert git(root, "rev-parse", "HEAD").startswith(head_sha(root))
    assert len(head_sha(root)) == 7


def test_head_todo_ids(make_repo: Callable[..., Path]) -> None:
    root = make_repo(
        message=(
            "subject\n\nbody\n\n"
            "Todo: 0123abcd\nTodo: 4567ef01 extra words\nTodo: ../../etc\n"
            "Signed-off-by: x <x@x>"
        )
    )
    assert head_todo_ids(root) == ["0123abcd", "4567ef01"]


def test_head_todo_ids_none(make_repo: Callable[..., Path]) -> None:
    assert head_todo_ids(make_repo()) == []


def test_run_check_exit_codes(tmp_path: Path) -> None:
    ok = run_check("exit 0", tmp_path)
    assert (ok.code, ok.timed_out, ok.passed) == (0, False, True)
    bad = run_check("exit 3", tmp_path)
    assert (bad.code, bad.passed) == (3, False)
    assert CHECK_TIMEOUT == 55


def test_run_check_uses_cwd_and_bash(tmp_path: Path) -> None:
    (tmp_path / "marker").write_text("x")
    assert run_check("test -f marker && [[ a == a ]]", tmp_path).passed


def test_run_check_timeout_kills_group(tmp_path: Path) -> None:
    start = time.monotonic()
    result = run_check("sleep 30 & wait", tmp_path, timeout=0.3)
    assert result.timed_out
    assert result.code is None
    assert not result.passed
    assert time.monotonic() - start < 5


def test_run_check_wrapper_prefixes_command(tmp_path: Path) -> None:
    log = tmp_path / "log"
    wrapper = tmp_path / "wrap.sh"
    wrapper.write_text(f'#!/bin/sh\necho "$1 $2" > "{log}"\nexec "$@"\n')
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IEXEC)
    assert run_check("exit 0", tmp_path, wrapper=wrapper).passed
    assert log.read_text().strip() == "bash -c"


def test_run_check_missing_shell_cwd(tmp_path: Path) -> None:
    result = run_check("true", tmp_path / "gone")
    assert result.code is None
    assert not result.timed_out
    assert not result.passed


def test_run_check_strips_git_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GIT_INDEX_FILE", "/nonexistent")
    monkeypatch.setenv("KEEP_ME", "1")
    assert run_check(
        'test -z "$GIT_INDEX_FILE" && test "$KEEP_ME" = 1', tmp_path
    ).passed


def test_describe(tmp_path: Path) -> None:
    assert run_check("exit 5", tmp_path).describe() == "exit 5"
    assert run_check("true", tmp_path / "gone").describe() == "could not start"
    assert (
        run_check("sleep 9", tmp_path, timeout=0.1).describe() == "timed out after 55s"
    )
