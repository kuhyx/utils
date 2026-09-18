"""Maven repositories: newest stable of `group:artifact`, from maven-metadata.

Three repositories, ALL asked: Google Maven (every `androidx.*` and
`com.android.*` artifact lives ONLY there), Maven Central and the Gradle
plugin portal (plugin marker artifacts `<id>:<id>.gradle.plugin`). The
version lists are pooled and the newest stable across them wins. Stopping at
the first repository that knew the artifact graded
`com.github.ben-manes:gradle-versions-plugin` current at 0.51.0 because
Central still carries its 2016 releases (0.11.1) while the plugin portal has
0.54.0 (2026-09-18). A 404 means "not here", not "not anywhere"; anything
else surfaces as `Offline` from the HTTP layer.

JitPack used to be the fourth: it served tag metadata for `com.github.*`
artifacts published nowhere else (PhotoView, DirectionalViewPager). Since
2026-09 that endpoint answers HTTP 401 "No access token" while the artifacts
themselves still download, so a `com.github.<owner>:<repo>` name that no
repository knows is answered from the GitHub repo's tags over `git
ls-remote` (unmetered, no token). JitPack's version IS the tag name, `v`
prefix included, so the tags are compared as they are.

`<latest>` and `<release>` in the metadata are not trusted: AndroidX writes
`1.2.0-alpha03` into `<latest>` routinely. The full `<versions>` list goes
through `newest_stable` like every other ecosystem. Only when NO repository
has a stable release at all does the newest pre-release become the reference
(`versions.reference`), which is how `androidx.biometric:biometric-ktx`,
alpha-only since 2021, gets a checkable answer. Google's API clients
(`v3-rev20260901-2.0.0`) are neither: for those the answer is the newest
revision of every generation, and the judge picks the pin's own.
"""

from __future__ import annotations

from xml.etree import ElementTree

from dep_freshness._tables import GITHUB_REMOTE, MAVEN_REPOS
from dep_freshness.registries._git import ls_remote
from dep_freshness.registries.gitcommit import source_repo
from dep_freshness.registries.http import get_text
from dep_freshness.versions import newest_per_generation, reference


def metadata_url(repo: str, name: str) -> str | None:
    """`.../group/path/artifact/maven-metadata.xml`, or None for a bad name."""
    group, sep, artifact = name.partition(":")
    if not sep or not group or not artifact:
        return None
    return f"{repo}{group.replace('.', '/')}/{artifact}/maven-metadata.xml"


def versions_in(xml: str) -> list[str]:
    """Every `<version>` in a maven-metadata document; [] when unparseable."""
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError:
        return []
    return [
        (node.text or "").strip()
        for node in root.iter("version")
        if node.text and node.text.strip()
    ]


def github_tags(name: str) -> list[str]:
    """Every tag of the GitHub repo behind a JitPack coordinate; [] otherwise."""
    repo = source_repo(name)
    if repo is None:
        return []
    lines = ls_remote(GITHUB_REMOTE.format(repo=repo), "--tags", "--refs")
    return [line.rpartition("refs/tags/")[2] for line in lines if "refs/tags/" in line]


def latest(name: str) -> str | None:
    seen: list[str] = []
    for repo in MAVEN_REPOS:
        url = metadata_url(repo, name)
        if url is None:
            return None
        body = get_text(url)
        if body is not None:
            seen.extend(versions_in(body))
    if not seen:
        seen.extend(github_tags(name))
    return reference(seen) or newest_per_generation(seen)
