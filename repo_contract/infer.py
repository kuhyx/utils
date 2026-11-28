"""Infer a proposed `## Commands` section from a repo's existing config."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from repo_contract.contract import KEYS, is_verbose
from repo_contract.sources import (
    MAKE_TARGETS,
    NPM_SCRIPTS,
    ci_commands,
    doc_commands,
    first_match,
    make_targets,
    package_scripts,
    read_text,
)
from repo_contract.stacks import has_tests

TEST_CHANGED = "scripts/test_changed.sh"
NO_TESTS = "n/a: no automated tests yet"
DROPPED = "n/a: dropped (kuhy, 2026-11-27)"
_VERBOSE_TOKEN = re.compile(r"\s(-v+|--verbose)(?=\s|$)")


@dataclass
class Proposal:
    """Contract values by key (already formatted) plus notes for the human."""

    stack: str
    values: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def lines(self) -> list[str]:
        """The `- key: value` lines in contract order."""
        return [f"- {k}: {self.values[k]}" for k in KEYS if k in self.values]


def quiet(command: str) -> str:
    """Strip verbose flags and add the tool's quiet default where known."""
    command = _VERBOSE_TOKEN.sub("", command)
    if "pytest" in command and not re.search(r"\s-q+\b", command):
        command = command.replace("pytest", "pytest -q", 1)
    if (
        "flutter test" in command
        and "--reporter" not in command
        and " -r " not in command
    ):
        command += " --reporter=compact"
    return (
        command
        if not is_verbose(command)
        else command.replace("--reporter=expanded", "")
    )


def _prefix(repo: Path) -> str:
    """How python tools are launched in this repo."""
    if (repo / "uv.lock").is_file():
        return "uv run"
    return "poetry run" if (repo / "poetry.lock").is_file() else "python3 -m"


def _pm(repo: Path) -> str:
    """Node package manager from the lockfile."""
    if (repo / "pnpm-lock.yaml").is_file():
        return "pnpm"
    return "yarn" if (repo / "yarn.lock").is_file() else "npm"


def stack_defaults(repo: Path, stack: str) -> dict[str, str]:
    """Conventional commands for the stack (lowest-priority source)."""
    py = _prefix(repo)
    pm = _pm(repo)
    table: dict[str, dict[str, str]] = {
        "python": {"test": f"{py} pytest -q"},
        "flutter": {"run": "flutter run", "test": "flutter test --reporter=compact"},
        "node": {"test": f"{pm} test --silent"},
        "go": {"test": "go test ./..."},
        "rust": {"test": "cargo test --quiet"},
        "gradle": {"test": "./gradlew test --quiet"},
        "godot": _godot_defaults(repo),
    }
    return table.get(stack, {})


def _godot_defaults(repo: Path) -> dict[str, str]:
    """Godot commands; the test runner comes from addons/ (GUT or gdUnit4)."""
    out = {"run": "godot --path ."}
    if (repo / "addons/gut/gut_cmdln.gd").is_file():
        out["test"] = "godot --headless -s addons/gut/gut_cmdln.gd -gexit -glog=0"
    elif (repo / "addons/gdUnit4").is_dir():
        out["test"] = (
            "godot --headless -s -d addons/gdUnit4/bin/GdUnitCmdTool.gd -a res://tests"
        )
    return out


def _run_default(repo: Path, stack: str) -> str:
    """Best guess for `run`, or an n/a with reason."""
    if stack == "python":
        for name in ("main.py", "__main__.py", "app.py"):
            if (repo / name).is_file():
                return f"python3 {name}"
        return "n/a: library (no entry point found)"
    if stack == "go":
        return (
            "go run ." if (repo / "main.go").is_file() else "n/a: library (no main.go)"
        )
    if stack == "rust":
        return (
            "cargo run"
            if (repo / "src" / "main.rs").is_file()
            else "n/a: library (no src/main.rs)"
        )
    if stack == "gradle":
        return (
            "./gradlew installDebug"
            if (repo / "app").is_dir()
            else "n/a: library (no app module)"
        )
    if stack == "node":
        return "n/a: library (no start/dev script)"
    return "n/a: collection of scripts, no single entry point"


def _pick(
    repo: Path, key: str, stack: str, doc: list[str], ci: list[str]
) -> tuple[str | None, str]:
    """(command, source) for one key by priority doc > Makefile > npm > CI > default."""
    found = first_match(key, doc)
    if found:
        return found, "CLAUDE.md"
    targets = make_targets(repo)
    for name in MAKE_TARGETS.get(key, ()):
        if name in targets:
            return f"make {name}", "Makefile"
    helper = repo / "scripts" / f"{key}.sh"
    if helper.is_file():
        return f"scripts/{key}.sh", "scripts/"
    scripts = package_scripts(repo) if stack == "node" else {}
    for name in NPM_SCRIPTS.get(key, ()):
        if name in scripts:
            return f"{_pm(repo)} run {name}", "package.json"
    found = first_match(key, ci)
    if found:
        return found, "CI workflow"
    return stack_defaults(repo, stack).get(key), "stack default"


def propose(repo: Path, stacks: list[str]) -> Proposal:
    """Build the proposal for the repo's primary stack."""
    stack = stacks[0] if stacks else "unknown"
    prop = Proposal(stack)
    doc = doc_commands(read_text(repo / "CLAUDE.md"))
    ci = ci_commands(repo)
    tested = has_tests(repo, stacks)
    cmd, src = _pick(repo, "run", stack, doc, ci)
    prop.values["run"] = _fmt(cmd or _run_default(repo, stack), prop, "run", src)
    for key in ("lint", "coverage", "coverage-gaps"):
        prop.values[key] = DROPPED
    if not tested and stack in {"godot", "shell", "unknown"}:
        for key in ("test", "test-changed"):
            prop.values[key] = NO_TESTS
        prop.notes.append("no tests detected: test chain proposed as n/a")
        return _order(prop)
    test, src = _pick(repo, "test", stack, doc, ci)
    prop.values["test"] = _fmt(test, prop, "test", src)
    prop.values["test-changed"] = f"`{TEST_CHANGED}`"
    if not tested:
        prop.notes.append("no tests detected, but the stack normally has them")
    return _order(prop)


def _fmt(command: str | None, prop: Proposal, key: str, source: str) -> str:
    """Format a command (quiet-ified) or a placeholder, noting the source."""
    if not command:
        prop.notes.append(f"{key}: could not infer, fill in")
        return "`<FILL IN>`"
    if command.startswith("n/a"):
        prop.notes.append(f"{key}: {command}")
        return command
    prop.notes.append(f"{key}: from {source}")
    return f"`{quiet(command)}`"


def _order(prop: Proposal) -> Proposal:
    """Keep values in contract order."""
    prop.values = {k: prop.values[k] for k in KEYS if k in prop.values}
    return prop
