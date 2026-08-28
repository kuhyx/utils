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


@pytest.fixture(autouse=True)
def no_shared_allowlist(tmp_path, monkeypatch) -> Path:
    """Point the fleet-wide allowlist at a path that does not exist.

    AUTOUSE for the same reason as `cache_dir`: repos inherit the real
    ~/utils/dependency-freshness.allowlist.yaml, so without this every test
    silently reads whatever is currently excused fleet-wide and starts
    depending on it.
    """
    # In its OWN directory, not tmp_path: the `repo` fixture is tmp_path, and
    # the gate exempts inherited entries from the rot check everywhere except
    # the repo that owns the shared file. Putting both in one directory makes
    # every test look like it is running inside utils.
    target = tmp_path / "shared" / "shared-allowlist.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DEP_FRESHNESS_SHARED_ALLOWLIST", str(target))
    return target


@pytest.fixture(autouse=True)
def cache_dir(tmp_path, monkeypatch) -> Path:
    """Point the on-disk registry snapshot at a scratch directory.

    AUTOUSE, and not negotiable: any code path that constructs a bare `Cache()`
    writes to the real ~/.cache/dep-freshness/registry.json otherwise. That
    already happened once -- a quarantine test seeded a fake answer for package
    "x" into the live cache, and the next run of the same test read its own
    pollution back and passed for the wrong reason.
    """
    target = tmp_path / "cache"
    monkeypatch.setenv("DEP_FRESHNESS_CACHE", str(target))
    return target


def write(root: Path, relative: str, body: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


STALE_PUBSPEC = """\
name: demo
environment:
  sdk: ^3.12.2
dependencies:
  http: 1.5.0
"""
CURRENT_PUBSPEC = STALE_PUBSPEC.replace("1.5.0", "1.6.0")
ALLOWLIST = "dependency-freshness.allowlist.yaml"


@pytest.fixture
def canned(monkeypatch, cache_dir):
    """One registry answer for every package the end-to-end fixtures declare.

    Deliberately NOT autouse: the resolver tests monkeypatch `_fetch`
    themselves, and a fixture that quietly re-patched it for the whole suite
    would make those tests pass against this table instead of their own.
    `run` depends on it, so every end-to-end test still gets it.
    """
    answers = {("pub", "http"): "1.6.0", ("toolchain", "dart"): "3.13.2"}
    monkeypatch.setattr(
        "dep_freshness.resolve._fetch",
        lambda eco, name: answers.get((eco, name)),
    )
    return answers


@pytest.fixture
def run(repo, monkeypatch, canned):
    """Invoke the CLI inside the throwaway repo and return its exit code.

    `check` is imported here rather than at module scope for the same reason
    as in `no_network`: the sys.path insert above is what makes the package
    importable, and a top-level import would run before it.
    """
    from dep_freshness import check

    assert canned, "the registry table must be patched before the CLI runs"

    def invoke(*argv):
        monkeypatch.chdir(repo)
        return check.main(list(argv))
    return invoke
