"""Registry adapters, driven by fixtures rather than the live internet.

Each ecosystem has one documented way to leak a pre-release into "latest";
these tests are the only thing that catches that, because a leak fails *green*
and the end-to-end run reports the repo as up to date.
"""

from __future__ import annotations

import pytest

from dep_freshness.registries import cargo, gomod, npmjs, pub, pypi


@pytest.fixture
def answer(monkeypatch):
    """Install a canned payload for the next `get_json` call."""
    def install(payload, module):
        monkeypatch.setattr(module, "get_json", lambda *_a, **_k: payload)
    return install


def test_npm_rejects_a_prerelease_published_to_dist_tags_latest(answer):
    answer({
        "dist-tags": {"latest": "3.0.0-rc.1"},
        "versions": {"2.4.1": {}, "3.0.0-rc.1": {}},
    }, npmjs)
    assert npmjs.latest("some-pkg") == "2.4.1"


def test_npm_uses_dist_tags_when_it_is_stable(answer):
    answer({"dist-tags": {"latest": "5.1.0"}, "versions": {"5.1.0": {}}}, npmjs)
    assert npmjs.latest("some-pkg") == "5.1.0"


def test_npm_missing_package_is_none(answer):
    answer(None, npmjs)
    assert npmjs.latest("nope") is None


def test_cargo_prefers_max_stable_over_max_version(answer):
    answer({"crate": {"max_version": "2.0.0-beta.3",
                      "max_stable_version": "1.0.229"}}, cargo)
    assert cargo.latest("serde") == "1.0.229"


def test_cargo_falls_back_to_unyanked_versions(answer):
    answer({
        "crate": {},
        "versions": [{"num": "1.2.0", "yanked": True}, {"num": "1.1.0"}],
    }, cargo)
    assert cargo.latest("thing") == "1.1.0"


def test_pub_uses_latest_when_stable(answer):
    answer({"latest": {"version": "1.6.0"}}, pub)
    assert pub.latest("http") == "1.6.0"


def test_pub_falls_back_when_latest_is_a_prerelease(answer):
    answer({
        "latest": {"version": "2.0.0-dev.1"},
        "versions": [{"version": "1.9.0"}, {"version": "2.0.0-dev.1"}],
    }, pub)
    assert pub.latest("thing") == "1.9.0"


def test_pypi_skips_versions_whose_files_are_all_yanked(answer):
    answer({
        "versions": ["1.0.0", "1.1.0"],
        "files": [
            {"filename": "pkg-1.0.0-py3-none-any.whl", "yanked": False},
            {"filename": "pkg-1.1.0-py3-none-any.whl", "yanked": True},
            {"filename": "pkg-1.1.0.tar.gz", "yanked": True},
        ],
    }, pypi)
    assert pypi.latest("pkg") == "1.0.0"


def test_pypi_ignores_prereleases(answer):
    answer({
        "versions": ["1.0.0", "2.0.0rc1"],
        "files": [
            {"filename": "pkg-1.0.0.tar.gz", "yanked": False},
            {"filename": "pkg-2.0.0rc1.tar.gz", "yanked": False},
        ],
    }, pypi)
    assert pypi.latest("pkg") == "1.0.0"


def test_pypi_falls_back_to_the_version_list_without_files(answer):
    answer({"versions": ["1.0.0", "1.4.2"]}, pypi)
    assert pypi.latest("pkg") == "1.4.2"


def test_go_rejects_incompatible_and_prerelease(answer):
    answer({"Version": "v3.0.0+incompatible"}, gomod)
    assert gomod.latest("example.com/m") is None
    answer({"Version": "v1.2.0-rc1"}, gomod)
    assert gomod.latest("example.com/m") is None


def test_go_strips_the_v_prefix(answer):
    answer({"Version": "v1.9.4"}, gomod)
    assert gomod.latest("example.com/m") == "1.9.4"
