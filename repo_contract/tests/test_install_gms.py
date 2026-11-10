"""A Flutter repo with an Android target gets the no-GMS-sign-in gate."""

from __future__ import annotations

import stat
import subprocess
from pathlib import Path

from repo_contract import install as inst
from repo_contract import install_gms as gms

from .conftest import write


def flutter_android(root: Path, sub: str = "") -> Path:
    """A Flutter project at `root/sub` with an android/ dir."""
    base = f"{sub}/" if sub else ""
    write(root, f"{base}pubspec.yaml", "name: x\n")
    write(root, f"{base}android/app/build.gradle.kts", "plugins {}\n")
    return root


def test_no_pubspec_means_no_gate(repo: Path) -> None:
    assert gms.plan_gms(repo) == []
    assert gms.install_gms(repo) == []


def test_pubspec_without_android_means_no_gate(repo: Path) -> None:
    write(repo, "pubspec.yaml", "name: x\n")
    assert gms.plan_gms(repo) == []


def test_root_flutter_android_gets_shim_and_hook(repo: Path) -> None:
    flutter_android(repo)
    assert gms.plan_gms(repo) == [str(gms.SHIM), gms.HOOK_PIECE]
    assert inst.install(repo)[-2:] == [str(gms.SHIM), gms.HOOK_PIECE]
    shim = repo / gms.SHIM
    assert shim.stat().st_mode & stat.S_IXUSR
    config = (repo / inst.PRECOMMIT).read_text(encoding="utf-8")
    assert f"id: {gms.HOOK_ID}" in config
    assert "always_run: true" in config
    assert gms.plan_gms(repo) == []
    assert gms.install_gms(repo) == []


def test_nested_app_dir_counts(repo: Path) -> None:
    flutter_android(repo, "app")
    assert gms.plan_gms(repo) == [str(gms.SHIM), gms.HOOK_PIECE]


def test_drifted_shim_is_rewritten_hook_kept(repo: Path) -> None:
    flutter_android(repo)
    gms.install_gms(repo)
    write(repo, gms.SHIM.as_posix(), "#!/bin/bash\nexit 0\n")
    assert gms.install_gms(repo) == [str(gms.SHIM)]


def test_utils_itself_is_never_given_a_shim(repo: Path) -> None:
    flutter_android(repo, "google_account_token")
    write(repo, "repo_contract/check.py")
    assert gms.plan_gms(repo) == []


def test_installed_shim_delegates_to_the_shared_gate(repo: Path) -> None:
    flutter_android(repo)
    write(repo, "pubspec.lock", "packages:\n  google_sign_in_android:\n")
    gms.install_gms(repo)
    utils_root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        ["bash", str(repo / gms.SHIM), str(repo)],
        capture_output=True,
        text=True,
        check=False,
        env={"UTILS_ROOT": str(utils_root), "PATH": "/usr/bin:/bin"},
    )
    assert proc.returncode == 1
    assert "google_account_token" in proc.stderr
