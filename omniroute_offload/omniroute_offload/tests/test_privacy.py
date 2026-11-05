from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from omniroute_offload import _privacy as privacy


def _git_repo(path: Path, remote: str | None) -> Path:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    if remote:
        subprocess.run(
            ["git", "-C", str(path), "remote", "add", "origin", remote], check=True
        )
    return path


@pytest.fixture
def cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "cache.json"
    monkeypatch.setattr(privacy, "CACHE", path)
    return path


@pytest.mark.parametrize(
    "name",
    [
        ".env",
        ".env.local",
        "server.pem",
        "id_rsa",
        "id_ed25519.pub",
        "api.key",
        "client_secret.json",
        "credentials.json",
        "app.keystore",
    ],
)
def test_denied_file_names(tmp_path: Path, name: str) -> None:
    assert privacy.path_refusal(tmp_path / name, home=tmp_path / "home") is not None


@pytest.mark.parametrize("sub", [".ssh", ".config", ".gnupg", ".aws", ".claude"])
def test_denied_home_dirs(tmp_path: Path, sub: str) -> None:
    home = tmp_path / "home"
    reason = privacy.path_refusal(home / sub / "x.txt", home=home)
    assert reason is not None
    assert sub in reason


def test_outside_repo_only_tmp_and_var_log() -> None:
    home = Path("/nonexistent-home")
    assert privacy.path_refusal(Path("/tmp/big.log"), home=home) is None
    assert privacy.path_refusal(Path("/var/log/pacman.log"), home=home) is None
    reason = privacy.path_refusal(home / "Documents/notes.txt", home=home)
    assert reason is not None
    assert "not in a public repo" in reason


def test_repo_without_remote_is_refused(tmp_path: Path, cache: Path) -> None:
    repo = _git_repo(tmp_path / "r", None)
    assert privacy.repo_refusal(repo) == f"{repo}: repo has no GitHub origin"


def test_non_github_remote_is_refused(tmp_path: Path, cache: Path) -> None:
    repo = _git_repo(tmp_path / "r", "https://gitlab.com/a/b.git")
    assert "no GitHub origin" in str(privacy.repo_refusal(repo))


@pytest.mark.parametrize(
    ("remote", "slug"),
    [
        ("https://github.com/kuhyx/utils.git", "kuhyx/utils"),
        ("git@github.com:kuhyx/utils.git", "kuhyx/utils"),
        ("https://github.com/kuhyx/utils", "kuhyx/utils"),
    ],
)
def test_github_slug(remote: str, slug: str) -> None:
    assert privacy.github_slug(remote) == slug


def test_public_repo_allowed_and_cached(
    tmp_path: Path, cache: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _git_repo(tmp_path / "r", "https://github.com/kuhyx/utils.git")
    calls: list[str] = []

    def fake(slug: str) -> str | None:
        calls.append(slug)
        return "PUBLIC"

    monkeypatch.setattr(privacy, "_gh_visibility", fake)
    assert privacy.repo_refusal(repo) is None
    assert privacy.repo_refusal(repo) is None
    assert calls == ["kuhyx/utils"]
    assert json.loads(cache.read_text())["kuhyx/utils"]["visibility"] == "PUBLIC"


def test_stale_cache_is_refreshed(
    tmp_path: Path, cache: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _git_repo(tmp_path / "r", "https://github.com/kuhyx/x.git")
    cache.write_text(
        json.dumps({"kuhyx/x": {"visibility": "PUBLIC", "at": time.time() - 2 * 86400}})
    )
    monkeypatch.setattr(privacy, "_gh_visibility", lambda _slug: "PRIVATE")
    assert "PRIVATE" in str(privacy.repo_refusal(repo))


def test_unknown_visibility_fails_closed(
    tmp_path: Path, cache: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _git_repo(tmp_path / "r", "https://github.com/kuhyx/x.git")
    monkeypatch.setattr(privacy, "_gh_visibility", lambda _slug: None)
    assert "unknown" in str(privacy.repo_refusal(repo))
    assert not cache.exists()


def test_corrupt_cache_is_ignored(
    tmp_path: Path, cache: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _git_repo(tmp_path / "r", "https://github.com/kuhyx/utils.git")
    cache.write_text("{not json")
    monkeypatch.setattr(privacy, "_gh_visibility", lambda _slug: "PUBLIC")
    assert privacy.repo_refusal(repo) is None


def test_gh_visibility_parses_and_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def ok(*_a: object, **_k: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 0, '{"visibility":"PUBLIC"}', "")

    def bad(*_a: object, **_k: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 1, "", "not found")

    def boom(*_a: object, **_k: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", ok)
    assert privacy._gh_visibility("a/b") == "PUBLIC"
    monkeypatch.setattr(subprocess, "run", bad)
    assert privacy._gh_visibility("a/b") is None
    monkeypatch.setattr(subprocess, "run", boom)
    assert privacy._gh_visibility("a/b") is None


def test_file_refusal_combines_path_and_repo(
    tmp_path: Path, cache: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    repo = _git_repo(home / "src/pub", "https://github.com/kuhyx/utils.git")
    (repo / "a.py").write_text("x")
    monkeypatch.setattr(privacy, "_gh_visibility", lambda _slug: "PUBLIC")
    assert privacy.file_refusal(repo / "a.py", home=home) is None
    (repo / ".env").write_text("x")
    assert privacy.file_refusal(repo / ".env", home=home) is not None
    priv = _git_repo(home / "src/priv", "https://github.com/kuhyx/secret.git")
    (priv / "b.py").write_text("x")
    monkeypatch.setattr(privacy, "_gh_visibility", lambda _slug: "PRIVATE")
    assert "PRIVATE" in str(privacy.file_refusal(priv / "b.py", home=home))


@pytest.mark.parametrize(
    "text",
    [
        "key sk-abcdefghijklmnopqrstuvwx",
        "ghp_" + "a" * 36,
        "github_pat_" + "a" * 30,
        "AKIA" + "A" * 16,
        "-----BEGIN OPENSSH " + "PRIVATE KEY-----",
        "AIza" + "a" * 35,
        "xoxb-1234567890-abc",
    ],
)
def test_secret_scan_hits(text: str) -> None:
    assert privacy.secret_refusal(f"log line\n{text}\n") is not None


def test_secret_scan_clean() -> None:
    assert privacy.secret_refusal("ERROR: disk full at 12:00\nsk-short") is None


def test_check_dir_main(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cache: Path
) -> None:
    assert privacy.check_dir_main([str(tmp_path)]) == 0
    monkeypatch.setattr(privacy, "SCRATCH_ROOTS", ())
    assert privacy.check_dir_main([str(tmp_path)]) == 2
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["free-llm-check-dir"])
    assert privacy.check_dir_main() == 2
