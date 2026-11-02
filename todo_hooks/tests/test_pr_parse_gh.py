"""Tests for the PR Todo-section parser and the gh wrapper."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from todo_hooks import gh
from todo_hooks.pr_parse import TodoItem, parse_todo_items
from todo_hooks.tests._fakes import BODY, FakeGh, make_pr

if TYPE_CHECKING:
    from pathlib import Path


def test_parse_items() -> None:
    assert parse_todo_items(BODY) == [
        TodoItem("Add retry to sync", "pytest -q tests/test_retry.py"),
        TodoItem("Document the flag", None),
        TodoItem("Star bullet", "true"),
    ]


@pytest.mark.parametrize(
    "body",
    ["", "no heading", "## Todos\n- x", "## Todo:\n\nprose only\n- late item"],
)
def test_parse_items_none(body: str) -> None:
    assert parse_todo_items(body) == []


def test_parse_items_variants() -> None:
    body = "### todo\n- | done_check: x\n-   Spaced |  done_check:   a | b  \n"
    assert parse_todo_items(body) == [TodoItem("Spaced", "a | b")]


def test_parse_items_stops_at_next_heading_and_survives_none() -> None:
    assert parse_todo_items("## Todo:\n- one\n# Next\n- two") == [TodoItem("one", None)]


def test_run_gh_success_failure_and_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = tmp_path / "gh"
    fake.write_text(
        '#!/bin/sh\nif [ "$1" = fail ]; then echo oops >&2; exit 1; fi\necho "[]"\n'
    )
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:/usr/bin")
    assert gh.run_gh(["ok"]) == "[]\n"
    with pytest.raises(gh.GhError, match="oops"):
        gh.run_gh(["fail"])
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    with pytest.raises(gh.GhError, match="not installed"):
        gh.run_gh(["ok"])


def test_run_gh_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = tmp_path / "gh"
    fake.write_text("#!/bin/sh\nsleep 20\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:/usr/bin")
    monkeypatch.setattr(gh, "GH_TIMEOUT", 0.3)
    with pytest.raises(gh.GhError, match="timed out"):
        gh.run_gh(["x"])


def test_merged_prs_parses_fields() -> None:
    fake = FakeGh({"abc": [make_pr(5), {"number": 6}]})
    prs = gh.merged_prs("kuhyx", "demo", "abc", fake)
    assert [(p.number, p.merged) for p in prs] == [(5, True), (6, False)]
    assert fake.calls[0] == ["api", "repos/kuhyx/demo/commits/abc/pulls"]
