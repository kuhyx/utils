"""JitPack artifacts pinned to a commit: "newest" is the default branch's HEAD.

Seven of TachiyomiSY's dependencies are `com.github.<owner>:<repo>` at a
short hash. No registry lists a "latest" for those, and a hash is not a
version, so the gate's question becomes the only one a commit pin admits:
is the pinned commit still what the source repository's default branch
points at? (kuhy, 2026-09-12: chosen over never-expiring allowlist entries.)

The answer is the full HEAD sha; `evaluate` compares by prefix so a 7-, 10-
or 40-character pin all work, and reports the first ten characters, which
is what JitPack accepts as a version.
"""

from __future__ import annotations

from dep_freshness._tables import GITHUB_REMOTE, JITPACK_GROUP_PREFIX
from dep_freshness.registries._git import ls_remote


def source_repo(name: str) -> str | None:
    """`owner/repo` behind a JitPack coordinate, or None for anything else.

    `com.github.mihonapp:image-decoder` -> `mihonapp/image-decoder`;
    `com.github.arkon.FlexibleAdapter:flexible-adapter` -> `arkon/FlexibleAdapter`
    (a multi-module build names the repo in the group, the module after the
    colon).
    """
    group, sep, artifact = name.partition(":")
    if not sep or not artifact or not group.startswith(JITPACK_GROUP_PREFIX):
        return None
    parts = group[len(JITPACK_GROUP_PREFIX) :].split(".")
    if not parts[0]:
        return None
    repo = parts[1] if len(parts) > 1 and parts[1] else artifact
    return f"{parts[0]}/{repo}"


def latest(name: str) -> str | None:
    """The default branch's HEAD sha, or None when `name` is not a JitPack pin."""
    repo = source_repo(name)
    if repo is None:
        return None
    for line in ls_remote(GITHUB_REMOTE.format(repo=repo), "HEAD"):
        sha, _, ref = line.partition("\t")
        if ref.strip() == "HEAD" and sha:
            return sha.strip()
    return None
