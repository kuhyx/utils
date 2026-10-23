"""The widened repo-contract hook `files:` and the sync that rolls it out."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from repo_contract import hook_sync
from repo_contract.bootstrap import TEMPLATES

from .conftest import write

OLD = r"        files: ^(CLAUDE\.md|AGENTS\.md|scripts/test_changed\.sh)$"
CONFIG = """repos:
  - repo: local
    hooks:
      - id: repo-contract
        name: repo contract
        entry: scripts/check_repo_contract.sh
        language: system
        pass_filenames: false
{files}
      - id: other
        entry: x
"""


def template_regex() -> re.Pattern[str]:
    hooks = yaml.safe_load((TEMPLATES / "pre-commit-snippet.yaml").read_text())
    return re.compile(hooks[0]["files"])


@pytest.mark.parametrize(
    "path",
    [
        "CLAUDE.md",
        "AGENTS.md",
        "scripts/test_changed.sh",
        "android/app/src/main/AndroidManifest.xml",
        "app/android/app/src/sandbox/AndroidManifest.xml",
        "android/app/build.gradle",
        "android/app/build.gradle.kts",
        "android/app/src/main/res/values/strings.xml",
        "linux/todo.desktop",
        "todo.desktop",
        "assets/icon/icon_foreground.png",
        "app/assets/icon/icon.png",
        "repo-contract.toml",
        "focus-owner/repo-contract.toml",
        "pubspec.yaml",
    ],
)
def test_template_fires_on_launcher_files(path: str) -> None:
    assert template_regex().search(path)


@pytest.mark.parametrize(
    "path",
    ["lib/main.dart", "docs/CLAUDE.md", "assets/icon/sub/x.png", "x.desktop.bak"],
)
def test_template_ignores_other_files(path: str) -> None:
    assert not template_regex().search(path)


def config(repo: Path, files: str = OLD) -> Path:
    return write(repo, ".pre-commit-config.yaml", CONFIG.format(files=files))


def test_status(tmp_path: Path) -> None:
    assert hook_sync.status(tmp_path) == "no hook"
    config(tmp_path)
    assert hook_sync.status(tmp_path) == "stale"
    config(tmp_path, hook_sync.template_line())
    assert hook_sync.status(tmp_path) == "current"


def test_dry_run_changes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = config(tmp_path).read_text()
    assert hook_sync.main([str(tmp_path)]) == 1
    assert (tmp_path / ".pre-commit-config.yaml").read_text() == before
    out = capsys.readouterr().out
    assert f"would update: {tmp_path}" in out
    assert "1 stale, 0 updated, 0 current, 0 without the hook" in out


def test_apply_rewrites_only_the_files_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = config(tmp_path)
    assert hook_sync.main(["--apply", str(tmp_path)]) == 0
    assert path.read_text() == CONFIG.format(files=hook_sync.template_line())
    assert f"updated: {tmp_path}" in capsys.readouterr().out
    assert hook_sync.main(["--apply", str(tmp_path)]) == 0
    assert "0 stale, 0 updated, 1 current" in capsys.readouterr().out


def test_hook_without_files_line_gets_one(tmp_path: Path) -> None:
    config(tmp_path, "        always_run: false")
    assert hook_sync.status(tmp_path) == "stale"
    hook_sync.main(["--apply", str(tmp_path)])
    assert hook_sync.status(tmp_path) == "current"


def test_default_roots_are_the_sweep_roots(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "a" / ".git").mkdir(parents=True)
    (tmp_path / "b" / ".git").mkdir(parents=True)
    config(tmp_path / "a", hook_sync.template_line())
    assert hook_sync.main([], roots=[tmp_path]) == 0
    out = capsys.readouterr().out
    assert f"current: {tmp_path / 'a'}" in out
    assert f"no hook: {tmp_path / 'b'}" in out
