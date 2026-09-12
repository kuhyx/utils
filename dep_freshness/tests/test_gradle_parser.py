"""Gradle version catalogs and the wrapper: every shape the fleet's forks use."""

from __future__ import annotations

from dep_freshness.parsers import gradle
from dep_freshness.tests.conftest import write

CATALOG = """\
[versions]
kotlin = "2.4.0"
compose = { strictly = "1.9.0" }
loose = { require = "[1.0,2.0)" }
preferred = { prefer = "3.3.3" }
empty = { }

[libraries]
inline = "io.coil-kt:coil:2.7.0"
noversion = "io.coil-kt:coil"
byref = { module = "org.jetbrains.kotlin:kotlin-reflect", version.ref = "kotlin" }
split = { group = "androidx.core", name = "core-ktx", version = "1.17.0" }
strict = { module = "androidx.compose:runtime", version.ref = "compose" }
ranged = { module = "org.example:ranged", version.ref = "loose" }
prefer = { module = "org.example:prefer", version.ref = "preferred" }
bom = { module = "org.junit.platform:junit-platform-launcher" }
dangling = { module = "org.example:dangling", version.ref = "nope" }
emptyref = { module = "org.example:emptyref", version.ref = "empty" }
nameless = { version = "1.0.0" }
number = 42
bare = "justaname"
richinline = { module = "org.example:rich", version = { strictly = "0.1.0" } }

[plugins]
agp = { id = "com.android.application", version = "9.3.2" }
kotlin-jvm = { id = "org.jetbrains.kotlin.jvm", version.ref = "kotlin" }
inline = "org.example.plugin:0.5.0"
noversion = "org.example.bare"
idless = { version = "1.0.0" }

[bundles]
coil = ["inline"]
"""


def _by_name(deps):
    return {d.name: d for d in deps}


def test_every_library_shape(tmp_path):
    deps = _by_name(
        gradle.parse_catalog(write(tmp_path, "libs.versions.toml", CATALOG))
    )
    assert deps["io.coil-kt:coil"].pinned == "2.7.0"
    assert deps["org.jetbrains.kotlin:kotlin-reflect"].pinned == "2.4.0"
    assert deps["androidx.core:core-ktx"].pinned == "1.17.0"
    assert deps["androidx.compose:runtime"].pinned == "1.9.0"
    assert deps["org.example:prefer"].pinned == "3.3.3"
    assert deps["org.example:rich"].pinned == "0.1.0"
    assert deps["org.example:ranged"].pinned is None
    assert deps["org.example:ranged"].constraint == "[1.0,2.0)"
    assert all(d.ecosystem == "maven" for d in deps.values())


def test_bom_managed_and_broken_entries_are_skipped(tmp_path):
    deps = _by_name(
        gradle.parse_catalog(write(tmp_path, "libs.versions.toml", CATALOG))
    )
    for absent in (
        "org.junit.platform:junit-platform-launcher",
        "org.example:dangling",
        "org.example:emptyref",
        ":",
    ):
        assert absent not in deps
    assert not any(d.name.startswith("io.coil-kt:coil:") for d in deps.values())
    assert "justaname" not in deps


def test_plugins_resolve_as_marker_artifacts(tmp_path):
    deps = _by_name(
        gradle.parse_catalog(write(tmp_path, "libs.versions.toml", CATALOG))
    )
    agp = deps["com.android.application:com.android.application.gradle.plugin"]
    assert agp.pinned == "9.3.2"
    kt = deps["org.jetbrains.kotlin.jvm:org.jetbrains.kotlin.jvm.gradle.plugin"]
    assert kt.pinned == "2.4.0"
    assert deps["org.example.plugin:org.example.plugin.gradle.plugin"].pinned == "0.5.0"
    assert not any("org.example.bare" in n for n in deps)
    assert not any(n.startswith(":") for n in deps)


def test_a_version_ref_points_the_fix_at_the_versions_table(tmp_path):
    path = write(tmp_path, "libs.versions.toml", CATALOG)
    deps = _by_name(gradle.parse_catalog(path))
    lines = path.read_text().splitlines()
    assert lines[deps["org.jetbrains.kotlin:kotlin-reflect"].line - 1].startswith(
        "kotlin ="
    )
    assert lines[deps["io.coil-kt:coil"].line - 1].startswith("inline =")


def test_unreadable_or_malformed_catalog_yields_nothing(tmp_path):
    assert gradle.parse_catalog(tmp_path / "missing.toml") == []
    assert gradle.parse_catalog(write(tmp_path, "bad.toml", "[versions\n")) == []


def test_wrapper_distribution_is_the_gradle_toolchain_pin(tmp_path):
    body = (
        "distributionBase=GRADLE_USER_HOME\n"
        "distributionUrl=https\\://services.gradle.org/distributions/gradle-9.6.1-bin.zip\n"
    )
    (dep,) = gradle.parse_wrapper(write(tmp_path, "gradle-wrapper.properties", body))
    assert (dep.ecosystem, dep.name, dep.pinned, dep.line) == (
        "toolchain",
        "gradle",
        "9.6.1",
        2,
    )


def test_wrapper_accepts_the_all_distribution_and_prereleases(tmp_path):
    body = "distributionUrl=https\\://x/gradle-9.7.0-rc-1-all.zip\n"
    (dep,) = gradle.parse_wrapper(write(tmp_path, "gradle-wrapper.properties", body))
    assert dep.constraint == "9.7.0-rc-1"


def test_wrapper_without_a_recognisable_url_is_unpinned(tmp_path):
    body = "distributionUrl=https\\://example.com/custom.zip\n"
    (dep,) = gradle.parse_wrapper(write(tmp_path, "gradle-wrapper.properties", body))
    assert dep.constraint == "" and dep.pinned is None


def test_wrapper_without_a_url_or_file_yields_nothing(tmp_path):
    assert (
        gradle.parse_wrapper(
            write(tmp_path, "gradle-wrapper.properties", "zipStoreBase=x\n")
        )
        == []
    )
    assert gradle.parse_wrapper(tmp_path / "missing.properties") == []
