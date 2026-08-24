"""The exemption predicates and namespace matcher."""

from __future__ import annotations

from pathlib import Path

import pytest

from md_naming import rules
from md_naming.tests.conftest import write


@pytest.mark.parametrize(
    "name",
    [
        "README.md",
        "CLAUDE.md",
        "CLAUDE-extra.md",
        "DOCS-x.md",
        "TODO-y.md",
        "DOCS.md",
        "TODO.md",
        "README.markdown",
    ],
)
def test_allowed_names(name: str) -> None:
    assert rules.has_allowed_name(Path(name))


@pytest.mark.parametrize(
    "name",
    [
        "notes.md",
        "readme.md",
        "Readme.md",
        "design.md",
        "MIGRATION.md",
        "refactor_claude_todo.md",
        "my-TODO.md",
    ],
)
def test_rejected_names(name: str) -> None:
    assert not rules.has_allowed_name(Path(name))


def test_is_markdown() -> None:
    assert rules.is_markdown(Path("a.md"))
    assert rules.is_markdown(Path("a.MD"))
    assert rules.is_markdown(Path("a.markdown"))
    assert not rules.is_markdown(Path("a.txt"))


def test_excluded_dir() -> None:
    assert rules.in_excluded_dir(Path("/r/node_modules/x.md"))
    assert rules.in_excluded_dir(Path("/r/build/x.md"))
    # "/build/" must not match a directory merely starting with "build".
    assert not rules.in_excluded_dir(Path("/r/buildings/x.md"))


def test_third_party() -> None:
    assert rules.is_third_party(Path("/home/kuhy/warriorjs/docs/x.md"))
    assert rules.is_third_party(
        Path("/home/kuhy/screen-locker-backup-20260705-200741/x.md")
    )
    assert not rules.is_third_party(Path("/home/kuhy/todo/x.md"))


def test_vendored_skill_bundle() -> None:
    assert rules.is_vendored(Path("/home/kuhy/todo/.agents/skills/a/SKILL.md"))
    assert not rules.is_vendored(Path("/home/kuhy/todo/docs/x.md"))


@pytest.mark.parametrize(
    "path",
    [
        "/r/.github/ISSUE_TEMPLATE.md",
        "/r/.projectmem/plan.md",
        "/r/.hippo/m.md",
        "/r/ios/Runner/x.md",
    ],
)
def test_exempt_subpaths(path: str) -> None:
    assert rules.is_exempt_subpath(Path(path))


def test_reserved_names() -> None:
    assert rules.is_reserved_name(Path("/r/SKILL.md"))
    assert rules.is_reserved_name(Path("/r/CONTRIBUTING.md"))
    assert rules.is_reserved_name(Path("/r/THIRD_PARTY_NOTICES.md"))
    assert not rules.is_reserved_name(Path("/r/notes.md"))


def test_generated() -> None:
    assert rules.is_generated(Path("/r/generated/x.md"))
    assert not rules.is_generated(Path("/r/docs/x.md"))


def test_is_exempt_combines_every_rule() -> None:
    assert rules.is_exempt(Path("/r/node_modules/a.md"))
    assert rules.is_exempt(Path("/home/kuhy/warriorjs/a.md"))
    assert rules.is_exempt(Path("/r/.agents/skills/a/SKILL.md"))
    assert rules.is_exempt(Path("/r/.github/a.md"))
    assert rules.is_exempt(Path("/r/CONTRIBUTING.md"))
    assert rules.is_exempt(Path("/r/generated/a.md"))
    assert not rules.is_exempt(Path("/home/kuhy/todo/docs/a.md"))


def test_is_todo() -> None:
    assert rules.is_todo(Path("TODO-x.md"))
    assert not rules.is_todo(Path("DOCS-x.md"))
    # Prefix alone is not enough; it must still be markdown.
    assert not rules.is_todo(Path("TODO-x.txt"))


def test_contains_marker(tmp_path: Path) -> None:
    marked = write(tmp_path, "a.md", "text\nREMOVE ME AFTER FINISH\n")
    plain = write(tmp_path, "b.md", "text\n")
    assert rules.contains_marker(marked)
    assert not rules.contains_marker(plain)


def test_contains_marker_unreadable(tmp_path: Path) -> None:
    """A path that cannot be read answers False rather than raising."""
    assert not rules.contains_marker(tmp_path / "missing.md")


@pytest.mark.parametrize("repo", [".nvm", ".oh-my-zsh", ".cargo", ".pyenv"])
def test_dotfile_clones_are_third_party(repo: str) -> None:
    """Clones of other people's projects living outside ~/<project>/.

    The 2026-08-24 migration renamed 5 files in nvm and ohmyzsh because a
    survey that walked only ~/*/ never saw them.
    """
    assert rules.is_third_party(Path(f"/home/kuhy/{repo}/README.md"))
