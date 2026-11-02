"""The on-demand bridge into leetcode-guard, and the boundary around it."""

from __future__ import annotations

import ast
import builtins
from pathlib import Path
import re
import sys
import types
from typing import TYPE_CHECKING, Any

import pytest

import leetcode_coach
from leetcode_coach import guard_bridge

if TYPE_CHECKING:
    from collections.abc import Callable

PACKAGE = Path(leetcode_coach.__file__).resolve().parent
DENIED = re.compile(
    r"_ledger.*|_balance|_debt|_harvest.*|_gate.*|_sync.*|_lock.*|_breakglass"
    r"|_escape.*|_snapshot_push"
)


def _guard(monkeypatch: pytest.MonkeyPatch, **modules: Any) -> None:
    """Install fake ``leetcode_guard._<name>`` modules."""
    monkeypatch.setitem(
        sys.modules, "leetcode_guard", types.ModuleType("leetcode_guard")
    )
    for name, attrs in modules.items():
        module = types.ModuleType(f"leetcode_guard.{name}")
        module.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, f"leetcode_guard.{name}", module)


class Client:
    username = "kuhy"

    @staticmethod
    def post(*_a: object) -> None:
        return None


def test_solved_slugs_asks_guards_checker_with_guards_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[Any] = []

    def check_solved(post: object, slugs: list[str]) -> Any:
        seen.append((post, slugs))
        return types.SimpleNamespace(solved={"a"})

    _guard(
        monkeypatch,
        _settings={"build_client": Client},
        _live_solved={"check_solved": check_solved},
    )
    assert guard_bridge.solved_slugs(("a", "b")) == frozenset({"a"})
    assert seen == [(Client.post, ["a", "b"])]


def test_recent_accepted_returns_guards_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    probe = object()

    def fetch(post: object, username: str) -> object:
        assert (post, username) == (Client.post, "kuhy")
        return probe

    _guard(
        monkeypatch,
        _settings={"build_client": Client},
        _submissions={"fetch_recent_ac": fetch},
    )
    assert guard_bridge.recent_accepted() is probe


def test_phone_id_token_connects_as_the_named_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def connect(app: str, *, timeout_seconds: float) -> Any:
        assert (app, timeout_seconds) == ("relay", 3)
        return types.SimpleNamespace(auth=types.SimpleNamespace(id_token=lambda: "tok"))

    _guard(monkeypatch, _snapshot_auth={"connect": connect})
    assert guard_bridge.phone_id_token("relay", timeout_seconds=3)() == "tok"


def test_a_missing_guard_is_a_named_error(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import: Callable[..., Any] = builtins.__import__
    for name in list(sys.modules):
        if name.startswith("leetcode_guard"):
            monkeypatch.delitem(sys.modules, name)

    def refuse(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith("leetcode_guard"):
            raise ModuleNotFoundError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse)
    with pytest.raises(
        guard_bridge.GuardUnavailableError, match="needs leetcode-guard"
    ):
        guard_bridge.solved_slugs(["a"])


def _static_guard_imports(path: Path) -> list[str]:
    found: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names if a.name.startswith("leetcode_guard")]
        elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
            "leetcode_guard"
        ):
            found.append(node.module or "")
    return found


def test_no_coach_module_imports_the_guard_statically() -> None:
    sources = [p for p in PACKAGE.rglob("*.py") if "tests" not in p.parts]
    offenders = {
        p.name: _static_guard_imports(p) for p in sources if _static_guard_imports(p)
    }
    assert not offenders


def test_the_walk_would_catch_a_static_import(tmp_path: Path) -> None:
    probe = tmp_path / "x.py"
    probe.write_text(
        "from leetcode_guard import _ledger\nimport leetcode_guard._gate\n",
        encoding="utf-8",
    )
    assert _static_guard_imports(probe) == ["leetcode_guard", "leetcode_guard._gate"]


def test_the_bridge_names_only_read_only_guard_modules() -> None:
    text = (PACKAGE / "guard_bridge.py").read_text(encoding="utf-8")
    named = set(re.findall(r"leetcode_guard\.\w+", text))
    assert named == guard_bridge.ALLOWED
    assert not [m for m in named if DENIED.fullmatch(m.split(".")[1])]
    assert DENIED.fullmatch("_ledger_io")
    assert DENIED.fullmatch("_harvest_run")
