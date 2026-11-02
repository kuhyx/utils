"""Fetching a statement by slug: package first, skill file second."""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from typing import TYPE_CHECKING

import pytest

import sql_drills as sd
from sql_drills import _lc_run

if TYPE_CHECKING:
    from pathlib import Path


def test_default_fetcher_uses_fetch_problem(monkeypatch: pytest.MonkeyPatch) -> None:
    module = SimpleNamespace(
        fetch=lambda slug: {"slug": slug, "content": "x"},
        render=lambda q, lang: f"{q['slug']}|{lang}",
    )
    monkeypatch.setattr(_lc_run, "_load_fetcher", lambda: module)
    assert _lc_run.default_fetch("two-sum", "mysql") == "two-sum|mysql"


def test_default_fetcher_refuses_unknown_or_premium(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = SimpleNamespace(fetch=lambda _s: None, render=lambda *_a: "")
    monkeypatch.setattr(_lc_run, "_load_fetcher", lambda: module)
    with pytest.raises(sd.ProblemUnavailableError, match="premium"):
        _lc_run.default_fetch("nope", "mysql")


@pytest.fixture
def no_package(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_lc_run, "PACKAGE", "no_such_package.fetch_problem")


@pytest.mark.usefixtures("no_package")
def test_load_fetcher_falls_back_to_the_skill_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    skill = tmp_path / "fetch_problem.py"
    skill.write_text("MARK = 'from-file'\n")
    monkeypatch.setattr(_lc_run, "FETCHER_PATH", skill)
    assert _lc_run._load_fetcher().MARK == "from-file"


@pytest.mark.usefixtures("no_package")
def test_load_fetcher_without_any_source_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(_lc_run, "FETCHER_PATH", tmp_path / "missing.py")
    with pytest.raises(sd.ProblemUnavailableError, match="fetch_problem"):
        _lc_run._load_fetcher()


def test_load_fetcher_prefers_the_package(monkeypatch: pytest.MonkeyPatch) -> None:
    pkg = ModuleType("fake_pkg_fetch_problem")
    monkeypatch.setitem(sys.modules, "fake_pkg_fetch_problem", pkg)
    monkeypatch.setattr(_lc_run, "PACKAGE", "fake_pkg_fetch_problem")
    assert _lc_run._load_fetcher() is pkg


def test_network_failure_is_unavailable_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(_slug: str) -> None:
        msg = "offline"
        raise OSError(msg)

    module = SimpleNamespace(fetch=boom, render=lambda *_a: "")
    monkeypatch.setattr(_lc_run, "_load_fetcher", lambda: module)
    with pytest.raises(sd.ProblemUnavailableError, match="offline"):
        _lc_run.default_fetch("x", "mysql")


def test_a_single_odd_token_is_a_statement_not_a_slug() -> None:
    with pytest.raises(sd.NoExamplesError):
        sd.run_problem("Example", "x", "mysql")
