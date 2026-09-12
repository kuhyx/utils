"""The `upstream:` predicate: does the fork's upstream still pin this version?

A fork cannot always take a release before the project it tracks does --
moko-resources 0.27.0 rewrites every string accessor across 300 files of
TachiyomiSY and would break each future upstream commit that adds a string.
"Wait for upstream" is the honest reason, and it is checkable: fetch the
upstream repository's copy of the SAME manifest, parse it with the same
parser, and compare the pin. Equal means the entry holds; different means
upstream moved and the entry is dead, which exits 2 like every other rotten
allowlist entry.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from dep_freshness._tables import GITHUB_RAW
from dep_freshness.discover import parse_manifest
from dep_freshness.models import Exception_, Finding
from dep_freshness.registries.http import get_text


def upstream_pin(entry: Exception_, finding: Finding, root: Path) -> str | None:
    """What `entry.upstream_repo` pins for this package in the same manifest.

    None when upstream has no such manifest or does not declare the package;
    `Offline` propagates from the transport so the caller can degrade.
    """
    try:
        relative = finding.dep.path.resolve().relative_to(root.resolve())
    except ValueError:
        return None
    body = get_text(GITHUB_RAW.format(repo=entry.upstream_repo, path=relative.as_posix()))
    if body is None:
        return None
    with tempfile.TemporaryDirectory() as scratch:
        copy = Path(scratch) / finding.dep.path.name
        copy.write_text(body, encoding="utf-8")
        for dep in parse_manifest(copy):
            if dep.ecosystem == finding.dep.ecosystem and dep.name == finding.dep.name:
                return dep.pinned or dep.constraint
    return None


def still_pins(entry: Exception_, finding: Finding, root: Path) -> bool:
    """True while upstream pins exactly the version the entry excuses."""
    return upstream_pin(entry, finding, root) == entry.pinned
