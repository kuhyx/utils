"""The one-shot migration's decision logic.

The moves have already run, but the rules that produced them are the record of
why 203 files are named what they are -- and two real bugs were found here by
dry-running: basename matching that would have rewritten vendored node_modules
files, and a path-boundary guard that silently skipped qualified references.
Both are pinned below.
"""

from __future__ import annotations

import pytest

from md_naming.migrate import classify
from md_naming.migrate.plan import HOME, auto_name, rewrite, slugify

TODO_250 = HOME / "todo" / "refactor_claude_todo.md"
NEW_250 = HOME / "todo" / "TODO-file-length-250.md"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("see refactor_claude_todo.md here", "see TODO-file-length-250.md here"),
        ("(refactor_claude_todo.md)", "(TODO-file-length-250.md)"),
        ("docs/refactor_claude_todo.md", "docs/TODO-file-length-250.md"),
    ],
)
def test_distinctive_name_is_rewritten(text: str, expected: str) -> None:
    assert rewrite(text, TODO_250, NEW_250) == expected


def test_longer_filename_is_not_rewritten() -> None:
    """The guard must not match the tail of a different filename."""
    text = "my_refactor_claude_todo.md.bak"
    assert rewrite(text, TODO_250, NEW_250) == text


def test_ambiguous_name_needs_qualifying_directory() -> None:
    """PLAN.md appears in unrelated repos, so a bare mention is left alone.

    Pinning the bug that would have rewritten 12 vendored copies of
    qs/.github/SECURITY.md during a dry run.
    """
    old = HOME / "roadside-assistance" / "PLAN.md"
    new = HOME / "roadside-assistance" / "DOCS-plan.md"
    assert rewrite("an unrelated PLAN.md", old, new) == "an unrelated PLAN.md"
    assert (
        rewrite("see roadside-assistance/PLAN.md", old, new)
        == "see roadside-assistance/DOCS-plan.md"
    )


def test_distinctive_name_matches_regardless_of_directory() -> None:
    """A name absent from AMBIGUOUS_NAMES is rewritten wherever it appears.

    SESSION_RESULTS.md is distinctive enough that no unrelated repo owns one,
    so it is matched unqualified -- which is what let `vmbox/README.md` be
    repaired. The narrowing in AMBIGUOUS_NAMES is reserved for names that
    genuinely collide (PLAN.md, README.md, SPEC.md).
    """
    old = HOME / "utils" / "vmbox" / "SESSION_RESULTS.md"
    new = HOME / "utils" / "vmbox" / "DOCS-session-results.md"
    assert (
        rewrite("vmbox/SESSION_RESULTS.md", old, new) == "vmbox/DOCS-session-results.md"
    )
    assert (
        rewrite("bare SESSION_RESULTS.md", old, new) == "bare DOCS-session-results.md"
    )


@pytest.mark.parametrize(
    ("stem", "expected"),
    [
        ("Hello World", "hello-world"),
        ("01-motion_tokens", "01-motion-tokens"),
        ("---", "untitled"),
    ],
)
def test_slugify(stem: str, expected: str) -> None:
    assert slugify(stem) == expected


def test_auto_name_defaults_to_docs() -> None:
    assert auto_name("todo/docs/whatever.md") == ("DOCS-whatever.md", "record")


def test_auto_name_fixes_readme_casing() -> None:
    """A misspelled README stays a README rather than entering DOCS."""
    assert auto_name("x/Readme.md") == ("README.md", "record")


def test_dopamine_ux_parts_are_tasks_but_index_is_not() -> None:
    """00-INDEX records the programme; 01-09 are its unstarted parts."""
    assert auto_name("utils/dopamine-ux/03-diet-guard.md")[1] == "task"
    assert auto_name("utils/dopamine-ux/00-INDEX.md")[1] == "record"


def test_classified_paths_do_not_overlap() -> None:
    """A file cannot be both a task and a record."""
    assert not set(classify.TASKS) & set(classify.RECORDS)


def test_deleted_files_are_not_also_renamed() -> None:
    deleted = set(classify.PROVEN_DONE) | set(classify.CLAIMED_DONE)
    assert not deleted & set(classify.TASKS)
    assert not deleted & set(classify.RECORDS)
