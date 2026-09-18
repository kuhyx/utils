"""Maven metadata across four repositories, and the Gradle release feed."""

from __future__ import annotations

from pathlib import Path

import pytest

from dep_freshness import discover
from dep_freshness.registries import maven
from dep_freshness.registries import toolchain as tc
from dep_freshness.registries.http import Offline
from dep_freshness.resolve import _toolchain_latest
from dep_freshness.tests.conftest import write

GOOGLE, CENTRAL, PORTAL = maven.MAVEN_REPOS


def metadata(*versions: str, latest: str | None = None) -> str:
    body = "".join(f"<version>{v}</version>" for v in versions)
    head = f"<latest>{latest}</latest>" if latest else ""
    return f"<metadata><versioning>{head}<versions>{body}</versions></versioning></metadata>"


@pytest.fixture
def repos(monkeypatch):
    """Canned bodies per metadata URL; anything unlisted is a 404."""
    table: dict[str, str] = {}
    monkeypatch.setattr(maven, "get_text", lambda url, *a, **k: table.get(url))
    return table


def test_metadata_url_shape():
    assert (
        maven.metadata_url(CENTRAL, "io.coil-kt:coil")
        == f"{CENTRAL}io/coil-kt/coil/maven-metadata.xml"
    )
    assert maven.metadata_url(CENTRAL, "nocolon") is None
    assert maven.metadata_url(CENTRAL, ":artifact") is None


def test_versions_in_ignores_blank_nodes_and_bad_xml():
    assert maven.versions_in(metadata("1.0", " ", "2.0")) == ["1.0", "2.0"]
    assert maven.versions_in("<metadata><versions>") == []


def test_google_is_asked_first_and_latest_tag_is_not_trusted(repos):
    repos[maven.metadata_url(GOOGLE, "androidx.core:core-ktx")] = metadata(
        "1.16.0", "1.17.0", "1.18.0-alpha03", latest="1.18.0-alpha03"
    )
    assert maven.latest("androidx.core:core-ktx") == "1.17.0"


def test_central_answers_when_google_has_no_such_artifact(repos):
    repos[maven.metadata_url(CENTRAL, "io.coil-kt:coil")] = metadata("2.6.0", "2.7.0")
    assert maven.latest("io.coil-kt:coil") == "2.7.0"


def test_plugin_markers_come_from_the_portal(repos):
    name = "org.example.plugin:org.example.plugin.gradle.plugin"
    repos[maven.metadata_url(PORTAL, name)] = metadata("0.5.0")
    assert maven.latest(name) == "0.5.0"


def test_a_repo_with_only_prereleases_does_not_stop_the_search(repos):
    repos[maven.metadata_url(GOOGLE, "g:a")] = metadata("1.0.0-beta01")
    repos[maven.metadata_url(CENTRAL, "g:a")] = metadata("0.9.0")
    assert maven.latest("g:a") == "0.9.0"


def test_every_repository_is_asked_and_the_newest_stable_across_them_wins(repos):
    """gradle-versions-plugin: Central stopped at 0.11.1 in 2016, the plugin
    portal carries 0.54.0. The first answer is not the answer."""
    name = "com.github.ben-manes:gradle-versions-plugin"
    repos[maven.metadata_url(CENTRAL, name)] = metadata("0.11", "0.11.1")
    repos[maven.metadata_url(PORTAL, name)] = metadata("0.53.0", "0.54.0")
    assert maven.latest(name) == "0.54.0"


def tags(monkeypatch, remote_tags: dict[str, list[str]]):
    """Serve `git ls-remote --tags --refs` for the GitHub remotes in `remote_tags`."""
    calls: list[tuple[str, ...]] = []

    def fake(remote, *args):
        calls.append((remote, *args))
        repo = remote.removeprefix("https://github.com/")
        if repo not in remote_tags:
            raise Offline(remote)
        return [f"{'0' * 40}\trefs/tags/{tag}" for tag in remote_tags[repo]]

    monkeypatch.setattr(maven, "ls_remote", fake)
    return calls


def test_jitpack_artifact_is_answered_from_the_repo_tags(repos, monkeypatch):
    """PhotoView was never published anywhere but JitPack, whose metadata
    endpoint now answers 401; the repo's tags are the same list. `v`-tags and
    bare tags both appear and the newest STABLE wins: a newer pre-release
    tag is skipped exactly as it would be in maven-metadata."""
    name = "com.github.chrisbanes:PhotoView"
    calls = tags(
        monkeypatch,
        {"chrisbanes/PhotoView": ["v1.3.1", "2.2.0", "2.3.0", "v3.0.0-beta1"]},
    )
    assert maven.latest(name) == "2.3.0"
    assert calls == [("https://github.com/chrisbanes/PhotoView", "--tags", "--refs")]


def test_a_project_named_tag_is_read_as_its_version(repos, monkeypatch):
    """`java-nat-sort` is tagged `natural-comparator-1.1`, not `1.1`."""
    name = "com.github.gpanther:java-nat-sort"
    tags(
        monkeypatch,
        {
            "gpanther/java-nat-sort": [
                "natural-comparator-1.0",
                "natural-comparator-1.1",
            ]
        },
    )
    assert maven.latest(name) == "natural-comparator-1.1"


def test_a_repository_answer_wins_over_the_tags(repos, monkeypatch):
    """A `com.github.*` artifact that Central knows is not a JitPack build."""
    name = "com.github.ben-manes.caffeine:caffeine"
    repos[maven.metadata_url(CENTRAL, name)] = metadata("3.1.8", "3.2.0")
    calls = tags(monkeypatch, {})
    assert maven.latest(name) == "3.2.0"
    assert calls == []


def test_prereleases_from_a_repository_skip_the_tag_lookup(repos, monkeypatch):
    """Something was found, just nothing stable: the repo answered, so the
    pre-release fallback applies and the tags are never consulted."""
    name = "com.github.x:y"
    repos[maven.metadata_url(CENTRAL, name)] = metadata("1.0.0-beta1")
    calls = tags(monkeypatch, {})
    assert maven.latest(name) == "1.0.0-beta1"
    assert calls == []


def test_a_tagless_repo_and_a_non_jitpack_name_are_none(repos, monkeypatch):
    calls = tags(monkeypatch, {"o/r": [], "o/s": ["HEAD-not-a-tag"]})
    assert maven.latest("com.github.o:r") is None
    assert maven.github_tags("g:a") == []
    assert calls == [("https://github.com/o/r", "--tags", "--refs")]


def test_an_unreachable_repo_is_offline(repos, monkeypatch):
    tags(monkeypatch, {})
    with pytest.raises(Offline):
        maven.latest("com.github.o:gone")


def test_a_package_with_no_stable_anywhere_falls_back_to_newest_prerelease(repos):
    """biometric-ktx has been alpha-only since 2021: the newest alpha is the
    reference, and a stable release in ANY repo would still win over it."""
    name = "androidx.biometric:biometric-ktx"
    repos[maven.metadata_url(GOOGLE, name)] = metadata(
        "1.2.0-alpha05", "1.4.0-alpha02", "1.3.0-alpha01"
    )
    assert maven.latest(name) == "1.4.0-alpha02"


def test_unknown_everywhere_or_malformed_name_is_none(repos):
    assert maven.latest("g:nowhere") is None
    assert maven.latest("bare") is None


def test_offline_propagates_from_the_transport(monkeypatch):
    def down(*_a, **_k):
        raise Offline("down")

    monkeypatch.setattr(maven, "get_text", down)
    with pytest.raises(Offline):
        maven.latest("g:a")


def test_gradle_latest_from_the_release_feed(monkeypatch):
    monkeypatch.setattr(tc, "get_json", lambda *_a, **_k: {"version": "9.7.1"})
    assert tc.gradle_latest() == "9.7.1"
    monkeypatch.setattr(tc, "get_json", lambda *_a, **_k: {"version": "10.0.0-rc-1"})
    assert tc.gradle_latest() is None
    monkeypatch.setattr(tc, "get_json", lambda *_a, **_k: None)
    assert tc.gradle_latest() is None


def test_the_resolver_routes_gradle_to_the_toolchain_feed(monkeypatch):
    monkeypatch.setattr(tc, "gradle_latest", lambda: "9.7.1")
    assert _toolchain_latest("gradle") == "9.7.1"


def test_discovery_routes_catalog_and_wrapper(tmp_path: Path):
    catalog = write(
        tmp_path, "gradle/libs.versions.toml", '[libraries]\nc = "g:a:1.0.0"\n'
    )
    wrapper = write(
        tmp_path,
        "gradle/wrapper/gradle-wrapper.properties",
        "distributionUrl=https\\://x/gradle-9.6.1-bin.zip\n",
    )
    assert [d.name for d in discover.parse_manifest(catalog)] == ["g:a"]
    assert [d.name for d in discover.parse_manifest(wrapper)] == ["gradle"]
