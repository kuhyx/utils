"""Shared fixtures. Nothing here may touch the network.

Every registry answer is a fixture: the gate's worst failure mode is reporting
"up to date" against a pre-release, and a test that hits the real registry
cannot pin that behaviour down.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A throwaway git repo, so git-ignore lookups behave as in real use."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Fail loudly if a test reaches for a socket instead of a fixture.

    Imported inside the fixture, not at module top: the sys.path insert above
    is what makes the package importable at all, and a top-level import after
    it is a lint violation this repo does not suppress.
    """
    from dep_freshness.registries import http

    def forbidden(*_args, **_kwargs):
        raise AssertionError("test tried to open a real connection")

    # Every host is reachable unless a test asked for offline mode, so
    # `--offline` behaves in tests exactly as it does in a real run.
    monkeypatch.setattr(
        http, "host_reachable", lambda _url: not http._forced_offline
    )
    monkeypatch.setattr(http, "urlopen", forbidden)
    http.reset_probes()
    http.force_offline(False)


@pytest.fixture
def cache_dir(tmp_path, monkeypatch) -> Path:
    """Point the on-disk registry snapshot at a scratch directory."""
    target = tmp_path / "cache"
    monkeypatch.setenv("DEP_FRESHNESS_CACHE", str(target))
    return target


def write(root: Path, relative: str, body: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path
