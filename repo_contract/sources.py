"""Where bootstrap reads existing commands from: doc, Makefile, package.json, CI."""

from __future__ import annotations

import json
import re
from pathlib import Path

PATTERNS: dict[str, re.Pattern[str]] = {
    "test": re.compile(
        r"pytest|flutter test|vitest|jest|go test|cargo (nextest|test)|gradlew.* test|bats"
    ),
    "lint": re.compile(
        r"ruff|flutter analyze|dart analyze|eslint|golangci|clippy|shellcheck|pre-commit run|ktlint"
    ),
    "coverage": re.compile(r"--cov|--coverage|llvm-cov|jacoco|coverage run"),
}
MAKE_TARGETS = {
    "run": ("run", "start", "dev"),
    "test": ("test", "tests", "check"),
    "lint": ("lint",),
    "coverage": ("coverage", "cov"),
}
NPM_SCRIPTS = {
    "run": ("start", "dev"),
    "test": ("test",),
    "lint": ("lint",),
    "coverage": ("coverage", "test:coverage", "test:cov"),
}
_SPAN = re.compile(r"`([^`\n]+)`")
_MAKE = re.compile(r"^([A-Za-z0-9_.-]+):(?!=)", re.MULTILINE)
_CI_RUN = re.compile(r"^\s*(?:-\s*)?run:\s*(\S.*?)\s*$")


def read_text(path: Path) -> str:
    """File text, or '' when absent/unreadable (sources are best-effort)."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def doc_commands(text: str) -> list[str]:
    """Backticked spans of a CLAUDE.md that look like commands (contain a space)."""
    return [s for s in _SPAN.findall(text) if " " in s and s[0] not in "/~"]


def make_targets(repo: Path) -> set[str]:
    """Target names defined in the repo's Makefile."""
    return set(_MAKE.findall(read_text(repo / "Makefile")))


def package_scripts(repo: Path) -> dict[str, str]:
    """`scripts` of package.json ({} if absent or malformed)."""
    try:
        data = json.loads(read_text(repo / "package.json"))
    except json.JSONDecodeError:
        return {}
    scripts = data.get("scripts") if isinstance(data, dict) else None
    return scripts if isinstance(scripts, dict) else {}


def ci_commands(repo: Path) -> list[str]:
    """Single-line `run:` commands from .github/workflows (no expressions)."""
    out: list[str] = []
    for wf in sorted((repo / ".github" / "workflows").glob("*.y*ml")):
        for line in read_text(wf).splitlines():
            match = _CI_RUN.match(line)
            if (
                match
                and "${{" not in match.group(1)
                and match.group(1) not in {"|", ">", "|-"}
            ):
                out.append(match.group(1))
    return out


def first_match(key: str, commands: list[str]) -> str | None:
    """First command matching the key's pattern."""
    pattern = PATTERNS.get(key)
    if pattern is None:
        return None
    for cmd in commands:
        covering = PATTERNS["coverage"].search(cmd) is not None
        if pattern.search(cmd) and (covering == (key == "coverage")):
            return cmd
    return None
