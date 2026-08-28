"""Flutter/Node release feeds, and the git-tag "registry" for shared libs."""

from __future__ import annotations

import subprocess

import pytest

from dep_freshness.registries import gittag
from dep_freshness.registries import toolchain as tc
from dep_freshness.registries.http import Offline

RELEASES = {
    "current_release": {"stable": "abc123", "beta": "def456"},
    "releases": [
        {"hash": "def456", "channel": "beta", "version": "3.48.0-0.1.pre"},
        {"hash": "abc123", "channel": "stable", "version": "3.47.2",
         "dart_sdk_version": "3.13.2"},
        {"hash": "old", "channel": "stable", "version": "3.47.1"},
    ],
}


@pytest.fixture
def feed(monkeypatch):
    def install(payload):
        monkeypatch.setattr(tc, "get_json", lambda *_a, **_k: payload)
    return install


def test_flutter_reads_the_current_stable_release(feed):
    feed(RELEASES)
    assert tc.flutter_latest() == ("3.47.2", "3.13.2")


def test_flutter_falls_back_to_the_newest_stable_when_the_hash_is_unknown(feed):
    payload = {**RELEASES, "current_release": {"stable": "missing"}}
    feed(payload)
    assert tc.flutter_latest() == ("3.47.2", None)


def test_flutter_with_no_feed_is_unknown(feed):
    feed(None)
    assert tc.flutter_latest() == (None, None)


def test_node_targets_lts_not_current(feed):
    """Read literally, "latest stable" means Current; the box runs LTS."""
    feed([
        {"version": "v25.1.0", "lts": False},
        {"version": "v24.20.0", "lts": "Iron"},
        {"version": "v24.18.0", "lts": "Iron"},
    ])
    assert tc.node_latest() == "24.20.0"
    assert tc.node_latest(channel="current") == "25.1.0"


def test_node_with_no_feed_is_unknown(feed):
    feed(None)
    assert tc.node_latest() is None


def test_python_reports_the_running_interpreter():
    import platform
    assert tc.python_installed() == platform.python_version()


LS_REMOTE = (
    "aaa\trefs/tags/crdt_sync_dart-v0.10.0\n"
    "bbb\trefs/tags/crdt_sync_dart-v0.11.0\n"
    "ccc\trefs/tags/crdt_sync_flutter-v0.2.1\n"
    "ddd\trefs/tags/design_system-v0.2.0\n"
)


@pytest.fixture
def ls_remote(monkeypatch):
    monkeypatch.setattr(gittag, "host_reachable", lambda _url: True)

    def install(stdout="", returncode=0, error=None):
        def fake_run(*_args, **_kwargs):
            if error:
                raise error
            return subprocess.CompletedProcess([], returncode, stdout, "")
        monkeypatch.setattr(subprocess, "run", fake_run)
    return install


def test_the_newest_tag_for_the_named_package_wins(ls_remote):
    ls_remote(LS_REMOTE)
    assert gittag.latest("crdt_sync_dart") == "0.11.0"


def test_another_packages_tags_are_not_confused_for_ours(ls_remote):
    ls_remote(LS_REMOTE)
    assert gittag.latest("crdt_sync_flutter") == "0.2.1"


def test_a_package_with_no_tags_has_no_latest(ls_remote):
    ls_remote(LS_REMOTE)
    assert gittag.latest("web_ui") is None


def test_a_failing_ls_remote_degrades_to_offline(ls_remote):
    ls_remote(returncode=128)
    with pytest.raises(Offline):
        gittag.latest("crdt_sync_dart")


def test_a_missing_git_binary_degrades_to_offline(ls_remote):
    ls_remote(error=OSError("no git"))
    with pytest.raises(Offline):
        gittag.latest("crdt_sync_dart")


def test_an_unreachable_remote_degrades_to_offline(monkeypatch):
    monkeypatch.setattr(gittag, "host_reachable", lambda _url: False)
    with pytest.raises(Offline):
        gittag.latest("crdt_sync_dart")
