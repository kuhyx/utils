"""Stack detection and a bounded "does this repo have tests" probe."""

from __future__ import annotations

import os
from pathlib import Path

PRUNE = frozenset(
    {
        ".git",
        ".utils",
        "node_modules",
        "build",
        ".dart_tool",
        ".venv",
        "venv",
        "target",
        "__pycache__",
        ".gradle",
        ".idea",
        "dist",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        "Pods",
        ".godot",
        "vendor",
        "third_party",
    }
)
MAX_DEPTH = 4
MAX_FILES = 5000

# stack -> marker files at the repo root (checked in order of this table).
MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("flutter", ("pubspec.yaml",)),
    ("godot", ("project.godot",)),
    (
        "gradle",
        ("build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"),
    ),
    ("python", ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt")),
    ("node", ("package.json",)),
    ("go", ("go.mod",)),
    ("rust", ("Cargo.toml",)),
)


def _walk(repo: Path) -> list[Path]:
    """Files under `repo` (pruned, depth- and count-bounded; never follows links)."""
    found: list[Path] = []
    base = len(repo.parts)
    for root, dirs, files in os.walk(repo, followlinks=False):
        dirs[:] = [d for d in dirs if d not in PRUNE]
        if len(Path(root).parts) - base >= MAX_DEPTH:
            dirs[:] = []
        found.extend(Path(root, f) for f in files)
        if len(found) >= MAX_FILES:
            break
    return found


def detect_stacks(repo: Path) -> list[str]:
    """Stacks present in `repo`, most specific first; `shell` if only scripts."""
    stacks = [s for s, names in MARKERS if any((repo / n).is_file() for n in names)]
    if not stacks and any(p.suffix == ".sh" for p in _walk(repo)):
        stacks.append("shell")
    return stacks


def _has_pattern(
    files: list[Path], suffixes: tuple[str, ...], names: tuple[str, ...]
) -> bool:
    """True when some file ends with a test suffix or sits under a test dir."""
    for path in files:
        if path.name.endswith(suffixes) or path.name.startswith(names):
            return True
    return False


def has_tests(repo: Path, stacks: list[str]) -> bool:
    """Whether the repo ships any automated tests (best-effort, bounded)."""
    files = _walk(repo)
    rels = [p.relative_to(repo) for p in files]
    in_test_dir = any(
        part in {"tests", "test", "spec", "__tests__"}
        for r in rels
        for part in r.parts[:-1]
    )
    named = _has_pattern(
        files,
        (
            "_test.py",
            "_test.dart",
            ".test.ts",
            ".test.js",
            ".test.tsx",
            ".spec.ts",
            ".spec.js",
            "_test.go",
            "Test.kt",
            "Test.java",
            ".bats",
            "_test.gd",
        ),
        ("test_",),
    )
    return in_test_dir or named or _node_test_script(repo, stacks)


def _node_test_script(repo: Path, stacks: list[str]) -> bool:
    """A real `scripts.test` in package.json (not npm's placeholder)."""
    if "node" not in stacks:
        return False
    try:
        text = (repo / "package.json").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return '"test"' in text and "no test specified" not in text
