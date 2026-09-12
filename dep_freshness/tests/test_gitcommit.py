"""JitPack commit pins: "newest" is the source repo's default-branch HEAD.

The fail-green case here is a hash the version parser cannot read: `behind`
returns False for unparseable input, so without its own ecosystem a moved
default branch would pass silently. Every path below is pinned down.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from dep_freshness.cache import ttl_for
from dep_freshness.evaluate import judge
from dep_freshness.models import Dep, Severity
from dep_freshness.parsers import gradle
from dep_freshness.registries import _git, gitcommit
from dep_freshness.registries.http import Offline
from dep_freshness.resolve import _LOOKUP, Answer
from dep_freshness.tests.conftest import write

HEAD = "844a07002c3d2f2b68a6b26a25e8e401777c73e7"


@pytest.fixture
def ls_remote(monkeypatch):
    monkeypatch.setattr(_git, "host_reachable", lambda _url: True)
    calls: list[list[str]] = []

    def install(stdout="", returncode=0, error=None):
        def fake_run(args, **_kwargs):
            calls.append(args)
            if error:
                raise error
            return subprocess.CompletedProcess(args, returncode, stdout, "")

        monkeypatch.setattr(subprocess, "run", fake_run)
        return calls

    return install


@pytest.mark.parametrize(
    "name,expected",
    [
        ("com.github.mihonapp:image-decoder", "mihonapp/image-decoder"),
        ("com.github.arkon.FlexibleAdapter:flexible-adapter", "arkon/FlexibleAdapter"),
        ("com.github.zhanghai.quickjs-java:quickjs-android", "zhanghai/quickjs-java"),
        ("com.github.owner.repo.deeper:module", "owner/repo"),
        ("com.github.owner.:module", "owner/module"),
        ("io.coil-kt:coil", None),
        ("com.github.:module", None),
        ("com.github.owner", None),
        ("com.github.owner:", None),
    ],
)
def test_the_github_repo_behind_a_jitpack_coordinate(name, expected):
    assert gitcommit.source_repo(name) == expected


def test_latest_is_the_default_branch_head(ls_remote):
    calls = ls_remote(f"{HEAD}\tHEAD\n{HEAD}\trefs/heads/master\n")
    assert gitcommit.latest("com.github.arkon.FlexibleAdapter:flexible-adapter") == HEAD
    assert calls[-1] == [
        "git",
        "ls-remote",
        "https://github.com/arkon/FlexibleAdapter",
        "HEAD",
    ]


def test_no_head_line_means_no_answer(ls_remote):
    ls_remote("\n  \nabc\trefs/heads/dev\n")
    assert gitcommit.latest("com.github.mihonapp:image-decoder") is None


def test_a_non_jitpack_coordinate_never_touches_git(ls_remote):
    calls = ls_remote(f"{HEAD}\tHEAD\n")
    assert gitcommit.latest("io.coil-kt:coil") is None
    assert calls == []


def test_ls_remote_failures_degrade_to_offline(ls_remote, monkeypatch):
    ls_remote(returncode=128)
    with pytest.raises(Offline):
        gitcommit.latest("com.github.mihon:unifile")
    ls_remote(error=OSError("no git"))
    with pytest.raises(Offline):
        gitcommit.latest("com.github.mihon:unifile")
    monkeypatch.setattr(_git, "host_reachable", lambda _url: False)
    with pytest.raises(Offline):
        gitcommit.latest("com.github.mihon:unifile")


CATALOG = """\
[versions]
unifile = "08f224c8f9"
photoView = "2.3.0"
tagged = "abc1234"

[libraries]
unifile = { module = "com.github.mihon:unifile", version.ref = "unifile" }
photoView = { module = "com.github.chrisbanes:PhotoView", version.ref = "photoView" }
inline = "com.github.mihonapp:image-decoder:e03b81e18a"
central = { module = "io.coil-kt:coil", version = "deadbeef" }
short = { module = "com.github.o:r", version = "abc12" }
tagged = { module = "org.example:lib", version.ref = "tagged" }
"""


def test_the_catalog_parser_tells_commit_pins_from_versions(tmp_path):
    deps = {
        d.name: d
        for d in gradle.parse_catalog(write(tmp_path, "libs.versions.toml", CATALOG))
    }
    assert (
        deps["com.github.mihon:unifile"].ecosystem,
        deps["com.github.mihon:unifile"].pinned,
    ) == (
        "gitcommit",
        "08f224c8f9",
    )
    assert deps["com.github.mihonapp:image-decoder"].ecosystem == "gitcommit"
    assert deps["com.github.chrisbanes:PhotoView"].ecosystem == "maven"
    assert deps["com.github.chrisbanes:PhotoView"].pinned == "2.3.0"
    # A hash-shaped version outside com.github.* is still a Maven version
    # (an unpinned one, since it is not exact), and six hex digits is too few.
    assert deps["io.coil-kt:coil"].ecosystem == "maven"
    assert deps["io.coil-kt:coil"].pinned is None
    assert deps["com.github.o:r"].ecosystem == "maven"
    assert deps["org.example:lib"].ecosystem == "maven"


def dep(pinned: str | None = "844a07002c") -> Dep:
    return Dep(
        ecosystem="gitcommit",
        name="com.github.arkon.FlexibleAdapter:flexible-adapter",
        constraint=pinned or "",
        path=Path("libs.versions.toml"),
        line=1,
        pinned=pinned,
    )


def test_a_pin_at_head_passes_whatever_its_length_or_case():
    assert judge(dep("844a07002c"), Answer(HEAD)) is None
    assert judge(dep("844A070"), Answer(HEAD)) is None
    assert judge(dep(HEAD), Answer(HEAD)) is None


def test_a_pin_behind_head_is_stale_and_reports_the_short_sha():
    finding = judge(dep("c8013533"), Answer(HEAD))
    assert finding.severity is Severity.STALE
    assert finding.latest == "844a07002c"
    assert "default branch has moved" in finding.detail


def test_a_missing_pin_is_reported_unpinned_with_head_to_use():
    finding = judge(dep(None), Answer(HEAD))
    assert finding.severity is Severity.UNPINNED
    assert "844a07002c" in finding.detail


def test_no_head_at_all_is_unknown_not_a_pass():
    assert judge(dep(), Answer(None)).severity is Severity.UNKNOWN


def test_commit_answers_cache_as_long_as_tags():
    assert ttl_for("gitcommit") == ttl_for("gittag") > ttl_for("maven")


def test_the_resolver_routes_gitcommit_to_the_git_registry():
    assert _LOOKUP["gitcommit"] is gitcommit.latest
