"""`devstats/run.sh`: tool setup, the compare run, the HTML report and its opener.

The autouse `isolated_git` fixture points HOME at a scratch dir, so the report
lands under it, `~/.claude/scripts/capped.sh` is absent (uncapped run) and the
real ~/data/devstats is never touched. Every run passes `--no-open` or puts a
recording `xdg-open` first on PATH, so nothing opens on kuhy's display.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from .conftest import DAY, lines

RUN_SH = Path(__file__).resolve().parents[1] / "run.sh"
# What run.sh needs besides python3 and git, for the stripped-PATH cases.
BASE_TOOLS = ("bash", "realpath", "dirname", "mkdir", "cat", "setsid", "env")


def run_sh(*args: str, path: str | None = None, cwd: Path | str = "/") -> subprocess.CompletedProcess[str]:
    """Run run.sh from an unrelated cwd (or `cwd`), optionally with a replaced PATH."""
    env = dict(os.environ)
    if path is not None:
        env["PATH"] = path
    return subprocess.run([str(RUN_SH), *args], cwd=cwd, env=env, capture_output=True, text=True,
                          check=False, timeout=50)


def report_path() -> Path:
    return Path(os.environ["HOME"]) / "data" / "devstats" / "report.html"


@pytest.fixture
def src(make_repo, tmp_path: Path) -> Path:
    """One repo with a fresh commit by kuhy's address."""
    repo = make_repo("app")
    repo.commit({"app.py": lines(30)}, int(time.time()) - DAY)
    return tmp_path / "src"


def test_run_prints_tables_writes_report_and_no_warnings(src: Path) -> None:
    proc = run_sh("--no-open", "--root", str(src))
    assert proc.returncode == 0, proc.stderr
    assert "## LoC per calendar day vs Cmdr" in proc.stdout
    assert "| 30 d | raw | 1 |" in proc.stdout  # 30 lines / 30 days
    assert proc.stdout.rstrip().endswith(f"report: {report_path()}")
    assert "warning:" not in proc.stderr
    page = report_path().read_text()
    assert page.startswith("<!doctype html>")
    assert 'class="chart"' in page


def test_run_from_inside_the_package_dir(src: Path) -> None:
    """`python -m` from devstats/ must not let a package module shadow the stdlib."""
    proc = run_sh("--no-open", "--root", str(src), cwd=RUN_SH.parent)
    assert proc.returncode == 0, proc.stderr
    assert report_path().read_text().startswith("<!doctype html>")


def test_empty_root_exits_2_and_writes_no_report(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    proc = run_sh("--no-open", "--root", str(empty))
    assert proc.returncode == 2
    assert f"devstats: no git repos under {empty}" in proc.stderr
    assert not report_path().exists()


def test_help_lists_own_and_compare_flags() -> None:
    proc = run_sh("--help")
    assert proc.returncode == 0
    for flag in ("--no-open", "--root", "--email", "--by-repo", "--write"):
        assert flag in proc.stdout, flag


def _recorder(bindir: Path, name: str, log: Path) -> None:
    """A fake `name` that appends its argv to `log` and exits 0."""
    exe = bindir / name
    exe.write_text(f'#!/bin/bash\necho "$*" >> "{log}"\n')
    exe.chmod(0o755)


def _wait_for(path: Path) -> str:
    """The detached opener writes its log a moment after run.sh exits."""
    deadline = time.monotonic() + 5
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    return path.read_text() if path.exists() else ""


def test_opens_report_only_without_no_open(src: Path, tmp_path: Path) -> None:
    bindir, log = tmp_path / "bin", tmp_path / "xdg-open.log"
    bindir.mkdir()
    _recorder(bindir, "xdg-open", log)
    path = f"{bindir}:{os.environ['PATH']}"
    assert run_sh("--no-open", "--root", str(src), path=path).returncode == 0
    assert run_sh("--root", str(tmp_path / "nothing"), path=path).returncode == 2
    time.sleep(0.3)
    assert not log.exists()
    assert run_sh("--root", str(src), path=path).returncode == 0
    assert _wait_for(log) == f"{report_path()}\n"


def _stripped_path(tmp_path: Path) -> Path:
    """A PATH dir holding only BASE_TOOLS: no python3, no git."""
    bindir = tmp_path / "shim"
    bindir.mkdir()
    for tool in BASE_TOOLS:
        found = shutil.which(tool)
        assert found, tool
        (bindir / tool).symlink_to(found)
    return bindir


def test_missing_tools_are_installed_with_pacman(tmp_path: Path) -> None:
    bindir, log = _stripped_path(tmp_path), tmp_path / "sudo.log"
    _recorder(bindir, "sudo", log)
    proc = run_sh("--no-open", path=str(bindir))
    assert log.read_text().splitlines() == ["pacman -S --needed python", "pacman -S --needed git"]
    assert proc.returncode == 3
    assert "devstats: python3 still missing after install" in proc.stderr


def test_old_python_is_refused(tmp_path: Path) -> None:
    bindir = _stripped_path(tmp_path)
    (bindir / "git").symlink_to(shutil.which("git") or "git")
    fake = bindir / "python3"
    fake.write_text("#!/bin/bash\necho 3.10\n")
    fake.chmod(0o755)
    proc = run_sh("--no-open", path=str(bindir))
    assert proc.returncode == 3
    assert "devstats: python3 >= 3.11 required, found 3.10" in proc.stderr
