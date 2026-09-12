"""`.file-length-exempt`: parsing, matching, and the fail-closed rule."""

from __future__ import annotations

from pathlib import Path

import pytest

from file_length.repo_exempt import (
    EXEMPT_FILE,
    ExemptFileError,
    Exemption,
    glob_to_regex,
    load,
    parse,
    repo_exempt_reason,
)
from file_length.tests.conftest import write


def test_parse_skips_blank_and_comment_lines() -> None:
    text = "\n# a comment\n  \napp/**/*.kt  # data tables\n"
    assert parse(text) == [Exemption("app/**/*.kt", "data tables")]


@pytest.mark.parametrize("line", ["app/x.kt", "app/x.kt #", "app/x.kt #   ", "# r"])
def test_parse_rejects_entries_without_a_reason(line: str) -> None:
    if line.startswith("#"):
        assert parse(line) == []  # a pure comment is not an entry
        return
    with pytest.raises(ExemptFileError, match=f"{EXEMPT_FILE}:1"):
        parse(line)


def test_parse_reports_the_offending_line_number() -> None:
    with pytest.raises(ExemptFileError, match=f"{EXEMPT_FILE}:3"):
        parse("a/*.kt # ok\n\nb/*.kt\n")


def test_load_without_file_is_empty(tmp_path: Path) -> None:
    assert load(tmp_path) == ()


def test_load_reads_and_memoises(tmp_path: Path) -> None:
    write(tmp_path, EXEMPT_FILE, "a/*.kt  # one\n")
    first = load(tmp_path)
    write(tmp_path, EXEMPT_FILE, "b/*.kt  # two\n")
    assert load(tmp_path) is first
    assert first == (Exemption("a/*.kt", "one"),)


def test_reason_none_when_repo_has_no_entries(tmp_path: Path) -> None:
    assert repo_exempt_reason(tmp_path / "a" / "x.kt", tmp_path) is None


def test_reason_matches_glob_and_double_star(tmp_path: Path) -> None:
    write(tmp_path, EXEMPT_FILE, "app/**/tags/*.kt  # tag data tables\n")
    hit = tmp_path / "app" / "src" / "exh" / "tags" / "Group.kt"
    miss = tmp_path / "app" / "src" / "exh" / "Other.kt"
    assert repo_exempt_reason(hit, tmp_path) == "repo exemption: tag data tables"
    assert repo_exempt_reason(miss, tmp_path) is None


def test_reason_none_for_paths_outside_root(tmp_path: Path) -> None:
    write(tmp_path, EXEMPT_FILE, "**/*.kt  # everything\n")
    outside = tmp_path.parent / "elsewhere.kt"
    assert repo_exempt_reason(outside, tmp_path) is None


@pytest.mark.parametrize(
    ("pattern", "hit", "miss"),
    [
        ("a/*.kt", "a/x.kt", "a/b/x.kt"),
        ("a/**/*.kt", "a/b/c/x.kt", "b/x.kt"),
        ("a/**/*.kt", "a/x.kt", "a/x.kts"),
        ("**/tags/*.kt", "tags/x.kt", "tags/sub/x.kt"),
        ("a/?.kt", "a/x.kt", "a/xy.kt"),
        ("a/**", "a/b/c.kt", "b/a"),
        ("a.b", "a.b", "axb"),
    ],
)
def test_glob_to_regex(pattern: str, hit: str, miss: str) -> None:
    regex = glob_to_regex(pattern)
    assert regex.match(hit), (pattern, hit)
    assert not regex.match(miss), (pattern, miss)
