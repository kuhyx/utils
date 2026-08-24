"""Perform the rename plan: git mv, insert markers, repair references.

Ordering matters and is not arbitrary. References are rewritten BEFORE the
moves land, in the same run, because a half-applied migration leaves the
harness pointing at files that no longer exist -- and ~/.claude/CLAUDE.md is
read on every session, so that window is not theoretical.

Dry-run is the default. Nothing moves without --apply.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - plain-script import path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from md_naming.config import MARKER
from md_naming.migrate.plan import REFERENCE_ROOTS, Move, Plan, rewrite
from md_naming.rules import in_excluded_dir, is_third_party

MARKER_BLOCK = f"\n{MARKER}\n"


def repo_of(path: Path) -> Path:
    """The git repo root owning `path`, or its parent if it is not in one."""
    try:
        result = subprocess.run(
            ["git", "-C", str(path.parent), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:  # pragma: no cover - git missing
        return path.parent
    if result.returncode != 0:
        return path.parent
    return Path(result.stdout.strip())


def git_mv(move: Move, *, apply: bool) -> str:
    """Move one file with git so history follows. Returns a log line."""
    if move.new.exists():
        return f"SKIP (target exists) {move.old} -> {move.new.name}"
    if not apply:
        return f"would mv {move.old} -> {move.new.name}"
    root = repo_of(move.old)
    result = subprocess.run(
        ["git", "-C", str(root), "mv", str(move.old), str(move.new)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Untracked files are not known to git; fall back to a plain rename
        # rather than skipping, so untracked TODOs migrate too.
        move.old.rename(move.new)
        return f"mv (untracked) {move.old} -> {move.new.name}"
    return f"mv {move.old} -> {move.new.name}"


def ensure_marker(path: Path, *, apply: bool) -> str | None:
    """Append the removal marker to a task file that lacks it."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if MARKER in text:
        return None
    if not apply:
        return f"would mark {path.name}"
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text + MARKER_BLOCK, encoding="utf-8")
    return f"marked {path.name}"


def reference_files(plan: Plan) -> list[Path]:
    """Every file that could mention a renamed path: docs plus harness config."""
    found: set[Path] = set()
    for root in REFERENCE_ROOTS:
        if root.is_file():
            found.add(root)
        elif root.is_dir():
            found.update(p for p in root.rglob("*.md") if p.is_file())
    for move in plan.moves:
        repo = repo_of(move.old)
        found.update(
            p
            for p in repo.rglob("*.md")
            if p.is_file() and not in_excluded_dir(p) and not is_third_party(p)
        )
    return sorted(found)


def repair_references(plan: Plan, *, apply: bool) -> list[str]:
    """Rewrite mentions of every renamed file. Returns log lines."""
    logs: list[str] = []
    targets = reference_files(plan)
    moved = {move.old for move in plan.moves}
    for path in targets:
        if path in moved:
            continue  # its own rename is handled by git_mv
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:  # pragma: no cover - unreadable
            continue
        updated = text
        touched: list[str] = []
        for move in plan.moves:
            if move.old.name in updated and move.old.name != move.new.name:
                updated = rewrite(updated, move.old, move.new)
                touched.append(move.old.name)
        if touched and updated != text:
            if apply:
                path.write_text(updated, encoding="utf-8")
            verb = "ref" if apply else "would ref"
            logs.append(f"{verb} {path}: {', '.join(sorted(set(touched)))}")
    return logs
