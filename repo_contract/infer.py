"""Infer a proposed `## Commands` section from a repo's existing config."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from repo_contract.contract import KEYS, LISTER, is_verbose
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
NO_COVERAGE = "n/a: no coverage tooling for this stack"
REPORTS = {
    "python": "coverage.xml",
    "flutter": "coverage/lcov.info",
    "node": "coverage/lcov.info",
    "go": "coverage.out",
    "rust": "lcov.info",
    "gradle": "build/reports/jacoco/test/jacocoTestReport.xml",
}
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
    cfg = read_text(repo / "pyproject.toml") + read_text(
        repo / ".pre-commit-config.yaml"
    )
    py = _prefix(repo)
    pm = _pm(repo)
    ruff = "ruff check ." if py == "python3 -m" else f"{py} ruff check ."
    table: dict[str, dict[str, str]] = {
        "python": {
            "test": f"{py} pytest -q",
            "lint": ruff if "ruff" in cfg else "pre-commit run --all-files",
            "coverage": f"{py} pytest -q --cov --cov-branch --cov-report=xml",
        },
        "flutter": {
            "run": "flutter run",
            "test": "flutter test --reporter=compact",
            "lint": "flutter analyze",
            "coverage": "flutter test --reporter=compact --coverage",
        },
        "node": {
            "test": f"{pm} test --silent",
            "lint": f"{pm} run lint",
            "coverage": f"{pm} test --silent --coverage",
        },
        "go": {
            "test": "go test ./...",
            "lint": "go vet ./...",
            "coverage": "go test -coverprofile=coverage.out ./...",
        },
        "rust": {
            "test": "cargo test --quiet",
            "lint": "cargo clippy --quiet",
            "coverage": "cargo llvm-cov --lcov --output-path lcov.info",
        },
        "gradle": {
            "test": "./gradlew test --quiet",
            "lint": "./gradlew lint --quiet",
            "coverage": "./gradlew jacocoTestReport --quiet",
        },
        "godot": _godot_defaults(repo),
        "shell": {"lint": "shellcheck scripts/*.sh", "coverage": NO_COVERAGE},
    }
    return table.get(stack, {})


def _godot_defaults(repo: Path) -> dict[str, str]:
    """Godot commands; the test runner comes from addons/ (GUT or gdUnit4)."""
    out = {"run": "godot --path .", "coverage": NO_COVERAGE}
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
    for key in ("run", "lint"):
        cmd, src = _pick(repo, key, stack, doc, ci)
        prop.values[key] = _fmt(
            cmd or (_run_default(repo, stack) if key == "run" else None), prop, key, src
        )
    if not tested and stack in {"godot", "shell", "unknown"}:
        for key in ("test", "test-changed", "coverage", "coverage-gaps"):
            prop.values[key] = NO_TESTS
        prop.notes.append("no tests detected: test chain proposed as n/a")
        return _order(prop)
    test, src = _pick(repo, "test", stack, doc, ci)
    prop.values["test"] = _fmt(test, prop, "test", src)
    prop.values["test-changed"] = f"`{TEST_CHANGED}`"
    cov, src = _pick(repo, "coverage", stack, doc, ci)
    prop.values["coverage"] = _fmt(cov, prop, "coverage", src)
    report = REPORTS.get(stack)
    if prop.values["coverage"].startswith("n/a"):
        prop.values["coverage-gaps"] = NO_COVERAGE
    elif report:
        prop.values["coverage-gaps"] = f"`{LISTER} {report}`"
    else:
        prop.values["coverage-gaps"] = "`<FILL IN>`"
        prop.notes.append("coverage-gaps: unknown report path, fill in")
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
