"""The agent-ready gate: build, then run the shared AgentReady checker."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from repo_contract import agent_ready_gate as gate

from .conftest import write
from .test_web import config, vite_repo


@pytest.fixture
def fake_checker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A stand-in check.sh that logs its argv and exits with $FAKE_RC."""
    log = tmp_path / "checker.log"
    script = write(
        tmp_path,
        "fake/check.sh",
        f'#!/bin/bash\necho "$@" >> {log}\nexit "${{FAKE_RC:-0}}"\n',
        0o755,
    )
    monkeypatch.setattr(gate, "CHECKER", script)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return log


def site(tmp_path: Path, body: str) -> Path:
    root = tmp_path / "site"
    root.mkdir()
    config(root, body)
    return root


def test_dist_builds_in_a_copy_then_checks(tmp_path: Path, fake_checker: Path) -> None:
    root = site(
        tmp_path,
        '[agent_ready]\ndist = "out"\nbuild = "mkdir -p out && touch out/built"\n'
        'install = "touch installed"\nact = true\n',
    )
    assert gate.main(["--repo", str(root)]) == 0
    assert not (root / "out").exists()
    assert not (root / "installed").exists()
    mode, checked, act = fake_checker.read_text().split("\n")[0].split(" ")
    assert (mode, Path(checked).name, act) == ("dist", "out", "--act")
    assert root not in Path(checked).parents
    assert gate.main(["--repo", str(root), "--install"]) == 0
    assert (root / "installed").exists()


LIVE_BUILD = (
    '[agent_ready]\ndist = "dist"\n'
    'build = "rm -rf dist && mkdir dist && echo built > dist/index.html"\n'
)


def _live_site(root: Path) -> Path:
    config(root, LIVE_BUILD)
    write(root, "dist/live.html", "served by caddy\n")
    write(root, "src/app.ts", "x\n")
    write(root, "node_modules/dep/index.js", "module.exports = 1\n")
    return root


def _assert_live_untouched(root: Path, log: Path) -> None:
    assert (root / "dist" / "live.html").read_text() == "served by caddy\n"
    assert not (root / "dist" / "index.html").exists()
    assert "index.html" in log.read_text()  # the copy WAS built and checked


@pytest.fixture
def listing_checker(fake_checker: Path) -> Path:
    """The fake checker also logs what the checked build dir contains."""
    script = gate.CHECKER
    script.write_text(script.read_text().replace('echo "$@"', 'echo "$@"; ls "$2"'))
    return fake_checker


def test_live_dist_untouched_without_git(tmp_path: Path, listing_checker: Path) -> None:
    root = _live_site(tmp_path / "site")
    assert gate.main(["--repo", str(root)]) == 0
    _assert_live_untouched(root, listing_checker)


def test_live_dist_untouched_in_git_repo(tmp_path: Path, listing_checker: Path) -> None:
    root = _live_site(tmp_path / "site")
    write(root, ".gitignore", "dist/\nnode_modules/\n")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / "src" / "gone.ts").write_text("x\n")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    (root / "src" / "gone.ts").unlink()  # tracked but deleted in the worktree
    config(root, LIVE_BUILD.replace("echo built", "ls node_modules/dep src"))
    assert gate.main(["--repo", str(root)]) == 0
    _assert_live_untouched(root, listing_checker)


def test_failed_build_fails_without_checking(
    tmp_path: Path, fake_checker: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = site(tmp_path, '[agent_ready]\ndist = "d"\nbuild = "echo boom; exit 7"\n')
    assert gate.main(["--repo", str(root)]) == 1
    assert "boom" in capsys.readouterr().err
    assert not fake_checker.exists()


def test_failed_install_fails(tmp_path: Path, fake_checker: Path) -> None:
    root = site(tmp_path, '[agent_ready]\ndist = "d"\ninstall = "exit 3"\n')
    assert gate.main(["--repo", str(root), "--install"]) == 1
    assert not fake_checker.exists()


def test_checker_failure_propagates(
    tmp_path: Path, fake_checker: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = site(tmp_path, '[agent_ready]\ndist = "d"\n')
    monkeypatch.setenv("FAKE_RC", "1")
    assert gate.main(["--repo", str(root)]) == 1


def test_url_mode_degrades_offline_unless_strict(
    tmp_path: Path,
    fake_checker: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = site(tmp_path, '[agent_ready]\nurl = "https://x.example"\n')
    monkeypatch.setenv("FAKE_RC", "3")
    assert gate.main(["--repo", str(root)]) == 0
    assert "DEGRADED" in capsys.readouterr().err
    assert gate.main(["--repo", str(root), "--strict"]) == 3
    assert fake_checker.read_text().splitlines()[0] == "url https://x.example"


def test_skip_and_no_site(
    tmp_path: Path, fake_checker: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = site(tmp_path, '[agent_ready]\nskip = "auth-gated"\n')
    assert gate.main(["--repo", str(root)]) == 0
    assert "auth-gated" in capsys.readouterr().out
    assert gate.main(["--repo", str(tmp_path / "fake")]) == 0
    assert not fake_checker.exists()


def test_unconfigured_web_repo_fails(tmp_path: Path, fake_checker: Path) -> None:
    root = vite_repo(tmp_path / "v")
    assert gate.main(["--repo", str(root)]) == 1


def test_bad_config_is_usage_error(tmp_path: Path, fake_checker: Path) -> None:
    root = site(tmp_path, "[agent_ready]\n")
    assert gate.main(["--repo", str(root)]) == 2


def test_pre_commit_in_ci_defers_to_the_workflow(
    tmp_path: Path,
    fake_checker: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = site(tmp_path, '[agent_ready]\ndist = "d"\nbuild = "exit 1"\n')
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert gate.main(["--repo", str(root)]) == 0
    assert "agent-ready workflow" in capsys.readouterr().out
    assert gate.main(["--repo", str(root), "--strict"]) == 1


@pytest.mark.skipif(not gate.CHECKER.exists(), reason="agent_ready not checked out")
def test_real_checker_fails_a_bare_build(tmp_path: Path) -> None:
    root = site(tmp_path, '[agent_ready]\ndist = "dist"\n')
    write(root, "dist/index.html", "<!doctype html><title>x</title><p>hi</p>")
    assert gate.main(["--repo", str(root)]) == 1
