"""Maven repositories: newest stable of `group:artifact`, from maven-metadata.

Three repositories, asked in order until one knows the artifact: Google
Maven (every `androidx.*` and `com.android.*` artifact lives ONLY there),
Maven Central, and the Gradle plugin portal (plugin marker artifacts
`<id>:<id>.gradle.plugin`). A 404 means "not here", not "not anywhere", so
it moves on; anything else surfaces as `Offline` from the HTTP layer.

`<latest>` and `<release>` in the metadata are not trusted: AndroidX writes
`1.2.0-alpha03` into `<latest>` routinely. The full `<versions>` list goes
through `newest_stable` like every other ecosystem.
"""

from __future__ import annotations

from xml.etree import ElementTree

from dep_freshness._tables import MAVEN_REPOS
from dep_freshness.registries.http import get_text
from dep_freshness.versions import newest_stable


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


def latest(name: str) -> str | None:
    for repo in MAVEN_REPOS:
        url = metadata_url(repo, name)
        if url is None:
            return None
        body = get_text(url)
        if body is None:
            continue
        stable = newest_stable(versions_in(body))
        if stable is not None:
            return stable
    return None
