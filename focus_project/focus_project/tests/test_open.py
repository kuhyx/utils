# Copyright (c) 2026 Krzysztof Rudnicki
"""``python -m focus_project.open``: the tutor focus screen plus the work URL."""

from __future__ import annotations

from datetime import date
import os
import stat
import subprocess
import sys
import time
from typing import TYPE_CHECKING

import pytest

import focus_project as fp
from focus_project import open as launcher

if TYPE_CHECKING:
    from pathlib import Path

START = date(2029, 12, 1)
END = date(2030, 2, 1)


def _script(path: Path, log: Path) -> None:
    """An executable stub that appends its argv (one line) to ``log``."""
    path.write_text(f'#!/bin/sh\necho "$@" >> "{log}"\n', encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


@pytest.fixture
def stubs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Path]:
    """Stub run.sh and xdg-open; each logs its arguments."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    logs = {"tutor": tmp_path / "tutor.log", "site": tmp_path / "site.log"}
    _script(tmp_path / "run.sh", logs["tutor"])
    _script(bindir / "xdg-open", logs["site"])
    monkeypatch.setenv("FOCUS_TUTOR_RUN", str(tmp_path / "run.sh"))
    monkeypatch.setenv("PATH", str(bindir) + os.pathsep + "/usr/bin:/bin")
    return logs


def _project(**fields: object) -> None:
    fp.create_project(
        "hr",
        name="HackerRank prep",
        start=START,
        end=END,
        replaces=["leetcode"],
        daily_minutes=120,
        unlock_minutes=30,
        site_patterns=["leetcode.com", "hackerrank.com"],
        **fields,  # type: ignore[arg-type]
    )


def _lines(log: Path, *, wait: bool = True) -> list[str]:
    """The log's lines; xdg-open is detached, so give a late line a moment."""
    if not wait:
        time.sleep(0.3)  # long enough for a wrongly started stub to log
    deadline = time.monotonic() + (3 if wait else 0)
    while not log.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def test_opens_tutor_focus_with_start_and_the_work_url(stubs: dict[str, Path]) -> None:
    _project(work_url="https://www.hackerrank.com/dashboard")
    assert launcher.main([]) == 0
    assert _lines(stubs["tutor"]) == ["--route /focus?start=1"]
    assert _lines(stubs["site"]) == ["https://www.hackerrank.com/dashboard"]


def test_work_url_falls_back_to_the_first_site_pattern(stubs: dict[str, Path]) -> None:
    _project()
    launcher.main([])
    assert _lines(stubs["site"]) == ["https://leetcode.com"]


@pytest.mark.parametrize(
    ("patterns", "want"),
    [
        (["*.example.com"], "https://example.com"),
        (["*", "ok.com"], "https://ok.com"),
        (["a*b.com"], None),
        ([], None),
    ],
)
def test_fallback_handles_wildcards(
    patterns: list[str], want: str | None, stubs: dict[str, Path]
) -> None:
    fp.create_project(
        "p",
        name="P",
        start=START,
        end=END,
        replaces=["leetcode"],
        daily_minutes=60,
        unlock_minutes=0,
        site_patterns=patterns,
    )
    launcher.main([])
    assert _lines(stubs["site"], wait=bool(want)) == ([want] if want else [])


def test_no_site_flag_opens_only_the_tutor(stubs: dict[str, Path]) -> None:
    _project(work_url="https://www.hackerrank.com/dashboard")
    assert launcher.main(["--no-site"]) == 0
    assert _lines(stubs["tutor"]) == ["--route /focus?start=1"]
    assert _lines(stubs["site"], wait=False) == []


def test_no_active_project_opens_the_tutor_without_start(
    stubs: dict[str, Path],
) -> None:
    assert launcher.main([]) == 0
    assert _lines(stubs["tutor"]) == ["--route /focus"]
    assert _lines(stubs["site"], wait=False) == []


def test_corrupt_registry_is_treated_as_no_project(
    stubs: dict[str, Path], data: Path
) -> None:
    data.mkdir(parents=True)
    (data / "projects.json").write_text("{nope", encoding="utf-8")
    assert launcher.main([]) == 0
    assert _lines(stubs["tutor"]) == ["--route /focus"]
    assert _lines(stubs["site"], wait=False) == []


def test_missing_tutor_launcher_still_opens_the_site(
    stubs: dict[str, Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _project(work_url="https://www.hackerrank.com/dashboard")
    monkeypatch.setenv("FOCUS_TUTOR_RUN", str(tmp_path / "gone.sh"))
    assert launcher.main([]) == 0
    assert _lines(stubs["site"]) == ["https://www.hackerrank.com/dashboard"]


def test_nothing_launchable_is_an_error(
    stubs: dict[str, Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("FOCUS_TUTOR_RUN", str(tmp_path / "gone.sh"))
    assert launcher.main([]) == 1


def test_missing_xdg_open_is_reported_not_raised(
    stubs: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _project(work_url="https://www.hackerrank.com/dashboard")
    monkeypatch.setenv("PATH", "/nonexistent")
    assert launcher.main([]) == 0
    assert _lines(stubs["tutor"]) == ["--route /focus?start=1"]


def test_runs_as_a_module(stubs: dict[str, Path], tmp_path: Path) -> None:
    done = subprocess.run(
        [sys.executable, "-m", "focus_project.open", "--no-site"],
        check=False,
        capture_output=True,
        timeout=30,
        env=os.environ,
    )
    assert done.returncode == 0, done.stderr
    assert _lines(stubs["tutor"]) == ["--route /focus"]


def test_xdg_open_failing_to_start_is_reported_not_raised(
    stubs: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _project(work_url="https://www.hackerrank.com/dashboard")

    def boom(*_a: object, **_k: object) -> None:
        raise OSError

    monkeypatch.setattr(launcher.subprocess, "Popen", boom)
    monkeypatch.setattr(launcher, "_open_tutor", lambda _route: True)
    assert launcher.main([]) == 0
