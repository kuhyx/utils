"""Tests for note parsing, the trust store and path defaults."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from todo_hooks.notes import clean_title, parse_detail, parse_list
from todo_hooks.paths import Paths
from todo_hooks.tests._fakes import detail, line
from todo_hooks.trust import add_trusted, check_hash, is_trusted, load_trusted

ID = "0123abcd-0000-4000-8000-000000000001"


def test_parse_list_rows_and_empty() -> None:
    text = line(ID, title="# First") + "\n" + line("ffff0000-x", "kuhyx/b", "Second")
    rows = parse_list(text)
    assert [(r.id8, r.repo, r.title) for r in rows] == [
        ("0123abcd", "kuhyx/demo", "First"),
        ("ffff0000", "kuhyx/b", "Second"),
    ]
    assert parse_list("no tasks match") == []
    assert parse_list("garbage line\n\n") == []


def test_parse_detail_fields() -> None:
    task = parse_detail(detail(ID, done_check="make test", text="# T\n\nbody line"))
    assert task.id == ID
    assert task.status == "todo"
    assert task.repo == "kuhyx/demo"
    assert task.done_check == "make test"
    assert task.title == "T"
    assert task.text.endswith("body line")
    assert not task.is_manual


def test_parse_detail_without_optional_fields() -> None:
    raw = f"id: {ID}\nstatus: todo\n---\nTitle only"
    task = parse_detail(raw)
    assert task.repo is None
    assert task.done_check is None
    assert task.title == "Title only"


def test_parse_detail_multiline_done_check() -> None:
    raw = f"id: {ID}\nstatus: todo\ndone_check: a &&\n  b\nby: claude\n---\nT"
    assert parse_detail(raw).done_check == "a &&\n  b"


def test_parse_detail_without_separator() -> None:
    task = parse_detail(f"id: {ID}\nstatus: todo")
    assert task.text == ""


@pytest.mark.parametrize(
    ("body", "manual"),
    [
        ("T\n\nCheck: manual", True),
        ("T\n\n  check:   Manual  \nmore", True),
        ("T\n\nCheck: manual-ish", False),
        ("T\n\nNot Check: manual", False),
    ],
)
def test_manual_marker(body: str, manual: bool) -> None:
    assert parse_detail(detail(ID, text=body)).is_manual is manual


def test_clean_title() -> None:
    assert clean_title("# Hello ") == "Hello"
    assert clean_title("Hello") == "Hello"


def test_check_hash_is_sha256_of_stripped_text() -> None:
    expected = hashlib.sha256(b"make test").hexdigest()
    assert check_hash("  make test\n") == expected


def test_trust_roundtrip(tmp_path: Path) -> None:
    file = tmp_path / "sub" / "trusted"
    assert load_trusted(file) == set()
    assert not is_trusted(file, "true")
    assert add_trusted(file, "true", "0123abcd kuhyx/demo") is True
    assert add_trusted(file, "true", "again") is False
    assert is_trusted(file, "true")
    assert not is_trusted(file, "false")
    assert check_hash("true") in file.read_text()


def test_trust_file_ignores_comments_and_blank(tmp_path: Path) -> None:
    file = tmp_path / "t"
    file.write_text(
        f"# header\n\n{check_hash('x')} # note\n  {check_hash('y').upper()}\n"
    )
    assert load_trusted(file) == {check_hash("x"), check_hash("y")}


def test_paths_default_and_env_overrides(tmp_path: Path) -> None:
    capped = tmp_path / ".claude" / "scripts" / "capped.sh"
    capped.parent.mkdir(parents=True)
    capped.write_text("#!/bin/sh\n")
    base = Paths.default({}, tmp_path)
    assert base.token_file == tmp_path / ".config/todo-mcp/client-token"
    assert base.trust_file == tmp_path / ".config/todo-hooks/trusted-checks"
    assert base.report_file == tmp_path / ".local/state/todo-drift/report.txt"
    assert base.src_root == tmp_path / "src"
    assert base.capped == capped
    env = {
        "TODO_HOOKS_TRUST_FILE": "/t",
        "TODO_HOOKS_REPORT": "/r",
        "TODO_HOOKS_SRC_ROOT": "/s",
        "TODO_MCP_TOKEN_FILE": "/k",
    }
    over = Paths.default(env, tmp_path / "nohome")
    assert (over.trust_file, over.report_file, over.src_root) == (
        Path("/t"),
        Path("/r"),
        Path("/s"),
    )
    assert over.token_file == Path("/k")
    assert over.capped is None


def test_parse_detail_ignores_text_before_metadata() -> None:
    assert parse_detail(f"stray line\nid: {ID}\n---\nT").id == ID
