"""The contract text: keys, the `## Commands` parser, entry validation."""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from pathlib import Path

KEYS: tuple[str, ...] = (
    "run",
    "test",
    "test-changed",
    "lint",
    "coverage",
    "coverage-gaps",
)
QUIET_KEYS = frozenset({"test", "test-changed", "lint", "coverage"})
HEADING = "## Commands"
LISTER = "coverage-gaps"

_ENTRY = re.compile(r"^[-*]\s+([a-z-]+):\s*(.*?)\s*$")
_CMD = re.compile(r"^`([^`]+)`")
_NA = re.compile(r"^n/a\s*(?::\s*(.*)|\(\s*(.*?)\s*\))\s*$")
_PLACEHOLDER = re.compile(r"<[A-Za-z][A-Za-z _-]*>|\bFILL IN\b|\bTODO\b|\.\.\.")
_VERBOSE = re.compile(r"^(-v+|--verbose|--reporter=expanded)$")
RUNNER_LINE = re.compile(
    r"pytest|flutter|jest|vitest|go test|cargo|gradlew|bats|npm|pnpm|yarn"
)


@dataclass(frozen=True)
class Entry:
    """One `- key: value` line: a command, or an n/a with its reason."""

    key: str
    command: str | None
    na_reason: str | None


def commands_section(text: str) -> list[str]:
    """Lines of the `## Commands` section (empty if absent); fences respected."""
    lines: list[str] = []
    inside = fenced = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
        elif not fenced and line.startswith("## "):
            inside = line.strip() == HEADING
            continue
        if inside:
            lines.append(line)
    return lines


def has_section(text: str) -> bool:
    """Whether a `## Commands` heading exists outside code fences."""
    fenced = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
        elif not fenced and line.strip() == HEADING:
            return True
    return False


def parse_entries(text: str) -> tuple[dict[str, Entry], list[str]]:
    """Entries by key plus syntax problems (duplicates, n/a without reason)."""
    entries: dict[str, Entry] = {}
    problems: list[str] = []
    for line in commands_section(text):
        match = _ENTRY.match(line)
        if not match or match.group(1) not in KEYS:
            continue
        key, value = match.group(1), match.group(2)
        if key in entries:
            problems.append(f"duplicate '- {key}:' entry")
            continue
        cmd, na = _CMD.match(value), _NA.match(value)
        if cmd:
            entries[key] = Entry(key, cmd.group(1).strip(), None)
        elif na and (na.group(1) or na.group(2) or "").strip():
            entries[key] = Entry(key, None, (na.group(1) or na.group(2)).strip())
        elif value.startswith("n/a"):
            problems.append(f"'- {key}:' n/a must carry a reason: 'n/a: <why>'")
        else:
            problems.append(f"'- {key}:' needs a backticked command or 'n/a: <why>'")
    return entries, problems


def is_verbose(command: str) -> bool:
    """True if the command carries a verbose flag (-v, --verbose, expanded)."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    return any(_VERBOSE.match(t) for t in tokens) or "--reporter expanded" in command


def verbose_in_script(text: str) -> bool:
    """Verbose flag on a runner invocation line of a shell script."""
    return any(
        is_verbose(line)
        for line in text.splitlines()
        if not line.lstrip().startswith("#") and RUNNER_LINE.search(line)
    )


def entry_problems(entry: Entry) -> list[str]:
    """Problems with a single command entry (placeholder, verbosity)."""
    if entry.command is None:
        return []
    out: list[str] = []
    if _PLACEHOLDER.search(entry.command):
        out.append(f"'- {entry.key}:' still holds a placeholder: {entry.command}")
    if entry.key in QUIET_KEYS and is_verbose(entry.command):
        out.append(
            f"'- {entry.key}:' must be quiet by default (verbose flag in: {entry.command})"
        )
    return out


def script_token(command: str, repo: Path) -> Path | None:
    """The first token of `command` that names an existing file in `repo`."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    for token in tokens:
        if "/" in token or token.endswith((".sh", ".py")):
            candidate = repo / token
            if candidate.is_file():
                return candidate
    return None
