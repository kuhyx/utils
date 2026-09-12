#!/usr/bin/env python3
"""Fail when code builds a ``~/<name>`` path that ``~`` may not contain.

Since the 2026-09-11 reorganisation, ``~`` holds exactly eleven visible
entries (``src``, ``vendor``, ``services``, ``data``, ``media``, ``games``,
``sdk``, ``archive``, ``inbox``, ``Downloads``, ``Documents``). Anything else
is swept to ``inbox/`` by home-tidy. So a program that assembles
``<home>/todo`` is writing to a path that either does not exist or is about
to be moved out from under it -- no allowlist of *old* names required, which
is what makes this gate durable as repos come and go.

Exit codes: 0 clean, 1 findings, 2 bad usage.

Usage:
    check.py <file> [<file> ...]   # pre-commit passes changed files
    check.py --all [<root>]        # whole tree, default cwd
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from home_paths.patterns import first_segments

# The eleven names ~ may hold, kept in step with system-maintenance's
# home-tidy.toml [root] allow. Dotfiles are never home-tidy's business, and
# a bare `~` with no segment resolves to home itself.
ALLOWED = frozenset(
    {
        "src",
        "vendor",
        "services",
        "data",
        "media",
        "games",
        "sdk",
        "archive",
        "inbox",
        "Downloads",
        "Documents",
    }
)

# Segments that are not really directories under kuhy's ~: filesystem roots,
# and the macOS/Windows home layouts that cross-platform code legitimately
# builds. Flagging `~/Library` in a mac branch is noise, not a finding.
IGNORED_SEGMENTS = frozenset(
    {
        "root",
        "usr",
        "etc",
        "opt",
        "tmp",
        "var",
        "home",
        "Library",
        "AppData",
        "Applications",
        "Developer",
    }
)

# Third-party trees. Their layout is not ours to police, and `~/Unity` in a
# vendored Unity MCP server is correct for the machine it was written for.
THIRD_PARTY_PARTS = frozenset({"mcp-servers", "vendor", "node_modules", "third_party", "vendored"})

# Test corpora spell pre-move paths on purpose -- system-maintenance's own
# manifest already protects its fixtures under `refs.skip_paths`, for the
# same reason: rewriting them turned six assertions into tautologies once.
TEST_PARTS = frozenset({"tests", "test", "testdata", "fixtures"})

# Leading comment markers. The migration's literal rewriter already handled
# prose; what survived it was *code*, so a path named in a comment is at
# worst doc rot and would otherwise swamp the gate (it was 60% of the first
# run's output, every one of them a sentence rather than a path).
COMMENT_PREFIXES = ("#", "//", "*", "--", "///", "/*")

CODE_SUFFIXES = frozenset(
    {
        ".py",
        ".dart",
        ".sh",
        ".bash",
        ".zsh",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".go",
        ".rs",
        ".toml",
        ".yaml",
        ".yml",
    }
)

PRUNE_DIRS = frozenset(
    {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        ".ci-mirror-venv",
        "build",
        ".dart_tool",
        "dist",
        ".mypy_cache",
        ".pytest_cache",
        "target",
    }
)

# A line carrying this marker is a deliberate reference to the old layout
# (a migration note, this checker's own tests) and is not a finding.
ALLOW_MARKER = "home-paths: allow"


@dataclass(frozen=True)
class Finding:
    """One home-relative path whose first segment cannot be right."""

    path: Path
    line_no: int
    segment: str
    pattern: str
    text: str

    def render(self, root: Path | None = None) -> str:
        """One grep-style line naming the file, the segment and the fix."""
        where = self.path
        if root is not None:
            try:
                where = self.path.relative_to(root)
            except ValueError:
                pass
        return (
            f"{where}:{self.line_no}: builds ~/{self.segment} — "
            f"~ holds only {', '.join(sorted(ALLOWED))}. "
            f"Did you mean ~/src/{self.segment}?  [{self.pattern}]\n"
            f"    {self.text.strip()}"
        )


def scan_text(path: Path, text: str) -> list[Finding]:
    """Every finding in ``text``, attributed to ``path``."""
    out: list[Finding] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if ALLOW_MARKER in line or line.lstrip().startswith(COMMENT_PREFIXES):
            continue
        seen: set[str] = set()
        for pattern, segment in first_segments(line):
            if segment in ALLOWED or segment in IGNORED_SEGMENTS:
                continue
            # Several spellings overlap -- `${HOME}/x` is both an `interp`
            # and an `fstring` -- and one path deserves one finding.
            if segment in seen:
                continue
            seen.add(segment)
            # `~/x`, `~/y` -- a one-character segment is a documentation
            # placeholder (docstrings explaining the path grammar), never a
            # real directory in this layout.
            if len(segment) == 1:
                continue
            out.append(Finding(path, line_no, segment, pattern, line))
    return out


def scan_file(path: Path) -> list[Finding]:
    """Findings in one file; unreadable or binary files yield none."""
    if path.suffix not in CODE_SUFFIXES or not path.is_file():
        return []
    if any(part in THIRD_PARTY_PARTS or part in TEST_PARTS for part in path.parts):
        return []
    if path.name.startswith("test_") or path.stem.endswith("_test"):
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    return scan_text(path, text)


def walk(root: Path) -> list[Path]:
    """Every candidate file under ``root``, pruned of caches and build output."""
    out: list[Path] = []
    for path in sorted(root.rglob("*")):
        if any(part in PRUNE_DIRS or part in THIRD_PARTY_PARTS for part in path.parts):
            continue
        if any(part in TEST_PARTS for part in path.parts):
            continue
        if path.name.startswith("test_") or path.stem.endswith("_test"):
            continue
        if path.suffix in CODE_SUFFIXES and path.is_file():
            out.append(path)
    return out


def main(argv: list[str]) -> int:
    """CLI: exit 1 on findings, 2 on bad usage."""
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    if argv[0] == "--all":
        root = Path(argv[1]).resolve() if len(argv) > 1 else Path.cwd()
        targets, base = walk(root), root
    else:
        targets, base = [Path(a) for a in argv], None

    findings = [f for target in targets for f in scan_file(target)]
    for finding in findings:
        print(finding.render(base))
    if findings:
        print(
            f"\n{len(findings)} home-relative path(s) point outside the ~ layout.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main(sys.argv[1:]))
