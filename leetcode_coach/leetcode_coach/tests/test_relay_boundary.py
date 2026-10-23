"""No relay route reaches the ledger (TODO-coach-ui.md decision 2, contract 4).

Walks the import closure of every ``leetcode_coach.relay`` module by AST --
through ``leetcode_coach`` and ``leetcode_guard`` alike, ``TYPE_CHECKING``
imports included -- and holds the guard side to an allowlist: the read-only
submission probe, its client, and the Firebase sign-in. A credit still comes
only from a LeetCode Accepted the harvester sees.
"""

from __future__ import annotations

import ast
from pathlib import Path
import re

import leetcode_coach

ROOT = Path(leetcode_coach.__file__).resolve().parent.parent
ALLOWED = {
    "_submissions",
    "_queries",
    "_settings",
    "_auth",
    "_constants",
    "_leetcode",
    "_throttle",
    "_snapshot_auth",
}
DENIED = re.compile(
    r"_ledger.*|_balance|_debt|_harvest.*|_gate.*|_sync.*|_lock.*|_breakglass"
    r"|_escape.*|_snapshot_push"
)
PACKAGES = ("leetcode_coach", "leetcode_guard")


def _file(module: str) -> Path | None:
    base = ROOT.joinpath(*module.split("."))
    for path in (base.with_suffix(".py"), base / "__init__.py"):
        if path.is_file():
            return path
    return None


def _imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
            found |= {f"{node.module}.{alias.name}" for alias in node.names}
    return {m for m in found if m.split(".")[0] in PACKAGES and _file(m)}


def closure() -> set[str]:
    """Every first-party module the relay package can load."""
    start = {
        f"leetcode_coach.relay.{p.stem}"
        for p in (ROOT / "leetcode_coach" / "relay").glob("*.py")
    }
    seen: set[str] = set()
    todo = sorted(start)
    while todo:
        module = todo.pop()
        if module in seen:
            continue
        seen.add(module)
        path = _file(module)
        assert path is not None, module
        todo += sorted(_imports(path) - seen)
    return seen


def test_the_relay_reaches_only_the_read_only_guard_modules() -> None:
    guard = {m.split(".")[1] for m in closure() if m.startswith("leetcode_guard.")}
    assert guard <= ALLOWED, guard - ALLOWED
    assert not [m for m in guard if DENIED.fullmatch(m)]
    assert "_submissions" in guard  # the walk does see the guard side


def test_the_walk_would_catch_a_ledger_import(tmp_path: Path) -> None:
    probe = tmp_path / "x.py"
    probe.write_text(
        "from leetcode_guard import _ledger\nimport leetcode_guard._gate\n",
        encoding="utf-8",
    )
    assert _imports(probe) >= {"leetcode_guard._ledger", "leetcode_guard._gate"}
    assert DENIED.fullmatch("_ledger_io")
    assert DENIED.fullmatch("_harvest_run")


def test_no_relay_module_spawns_anything_but_claude_and_node() -> None:
    relay = ROOT / "leetcode_coach" / "relay"
    spawning = {
        p.name
        for p in relay.glob("*.py")
        if re.search(r"\bsubprocess\b|os\.system|os\.exec|Popen", p.read_text())
    }
    assert spawning == {"runcode.py"}  # claude runs via claude_cli.ask
