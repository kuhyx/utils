"""Maven metadata across three repositories, and the Gradle release feed."""

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
