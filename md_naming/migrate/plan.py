"""Build the rename plan: old path -> new path, plus every inbound reference.

Renaming without fixing references is worse than the drift being fixed: the
user's own always-on instructions name specific paths (~/.claude/CLAUDE.md
points at todo/docs/llm-design-spec-audit.md), so a bare `git mv` would break
the harness config that tells Claude how to work.

This module only computes. :mod:`md_naming.migrate.apply` performs the moves.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from md_naming.migrate import classify

HOME = Path("/home/kuhy")

#: Trees searched for references to a renamed file, beyond the repos
#: themselves. These hold instructions that are loaded on every session, so a
#: stale path here silently misconfigures future work.
REFERENCE_ROOTS = (
    HOME / ".claude" / "CLAUDE.md",
    HOME / ".claude" / "rules",
    HOME / ".claude" / "skills",
    HOME / ".claude" / "memories",
    HOME / ".claude" / "projects" / "-home-kuhy" / "memory",
)


@dataclass
class Move:
    """One file rename, with the marker decision that goes with it."""

    old: Path
    new: Path
    kind: str  # "task" or "record"

    @property
    def needs_marker(self) -> bool:
        """Task files carry the removal marker; records never do."""
        return self.kind == "task"


@dataclass
class Plan:
    """Every move, plus the files that mention any of them."""

    moves: list[Move] = field(default_factory=list)
    unresolved: list[Path] = field(default_factory=list)

    def by_old_name(self) -> dict[str, Move]:
        return {str(move.old): move for move in self.moves}


def _target(old: Path, new_name: str) -> Path:
    """`new_name` placed in the same directory as `old`."""
    return old.parent / new_name


def build(extra_tasks: dict[str, str], extra_records: dict[str, str]) -> Plan:
    """The full rename plan, audited entries first then the triaged rest."""
    plan = Plan()
    tasks = {**classify.TASKS, **extra_tasks}
    records = {**classify.RECORDS, **extra_records}

    for rel, new_name in sorted(tasks.items()):
        old = HOME / rel
        if old.is_file():
            plan.moves.append(Move(old, _target(old, new_name), "task"))
        else:
            plan.unresolved.append(old)

    for rel, new_name in sorted(records.items()):
        old = HOME / rel
        if old.is_file():
            plan.moves.append(Move(old, _target(old, new_name), "record"))
        else:
            plan.unresolved.append(old)

    return plan


#: Basenames too generic to rewrite on the bare name. "PLAN.md" and
#: "RESEARCH.md" appear in unrelated repos and in vendored node_modules, so
#: matching them by name alone corrupts files the migration never touched --
#: observed in a dry run against 12 qs/.github/SECURITY.md copies.
AMBIGUOUS_NAMES = frozenset(
    {
        "PLAN.md",
        "TODO.md",
        "RESEARCH.md",
        "SPEC.md",
        "README.md",
        "CONTEXT.md",
        "SUMMARY.md",
        "MIGRATION.md",
        "design.md",
        "NEXT_SESSION.md",
        "DESIGN_AUDIT_TODO.md",
    }
)


def reference_pattern(old: Path, *, repo: Path | None = None) -> re.Pattern[str]:
    """Matches mentions of `old` that are specific enough to be safe.

    A distinctive basename ("refactor_claude_todo.md") is matched on its own,
    because cross-doc links are usually written with no directory at all. A
    generic one ("PLAN.md") is matched only when qualified by at least one
    parent directory, so an unrelated repo's own PLAN.md is left alone.
    """
    # The guard rejects only characters that would make this the tail of a
    # LONGER filename (my_refactor_claude_todo.md). "/" and "." are legitimate
    # separators in a path reference, so they must not block a match.
    if old.name not in AMBIGUOUS_NAMES:
        return re.compile(rf"(?<![\w-]){re.escape(old.name)}")
    # The guard applies to the start of the *qualified* string, so the "/"
    # joining dir and basename must not itself be treated as a preceding
    # path character -- that is what made "vmbox/SESSION_RESULTS.md" fail.
    qualified = f"{old.parent.name}/{old.name}"
    return re.compile(rf"(?<![\w-]){re.escape(qualified)}")


def rewrite(text: str, old: Path, new: Path) -> str:
    """`text` with safe mentions of `old` pointing at `new`."""
    if old.name not in AMBIGUOUS_NAMES:
        return reference_pattern(old).sub(new.name, text)
    return reference_pattern(old).sub(f"{old.parent.name}/{new.name}", text)


#: The remaining files are plain reference docs, renamed mechanically to
#: DOCS-<existing-slug>.md. The one exception is the dopamine-ux programme:
#: 00-INDEX records 8 of its 9 parts as "not started", so those parts are
#: outstanding work and become TODO, not DOCS. The index itself is a record.
AUTO_TASK_PREFIXES = ("utils/dopamine-ux/0",)


def slugify(stem: str) -> str:
    """A filename stem reduced to a lowercase, hyphenated slug."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", stem).strip("-").lower()
    return slug or "untitled"


def auto_name(rel: str) -> tuple[str, str]:
    """(new filename, kind) for a file with no explicit classification."""
    stem = Path(rel).stem
    # A misspelled README is a README, not a doc needing a new namespace.
    if stem.lower() == "readme":
        return "README.md", "record"
    if rel.startswith(AUTO_TASK_PREFIXES) and "INDEX" not in stem:
        return f"TODO-{slugify(stem)}.md", "task"
    return f"DOCS-{slugify(stem)}.md", "record"


def add_auto(plan: Plan, remaining: list[str]) -> None:
    """Extend `plan` with mechanical renames for unclassified files."""
    for rel in sorted(remaining):
        old = HOME / rel
        if not old.is_file():
            plan.unresolved.append(old)
            continue
        new_name, kind = auto_name(rel)
        target = _target(old, new_name)
        if target == old:
            continue
        plan.moves.append(Move(old, target, kind))
