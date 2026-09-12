"""Google API clients: `v3-rev20260901-2.0.0` is ordered inside its generation.

The fail-green case: read loosely, every `v3-rev...` is "3", and a 2019 pin
compares equal to a 2026 revision. The fail-red case: `v2-...-2.0.0` read as
newer than `v3-...-1.25.0` because 2.0.0 > 1.25.0.
"""

from __future__ import annotations

from pathlib import Path

from dep_freshness.evaluate import judge
from dep_freshness.models import Dep, Severity
from dep_freshness.registries import maven
from dep_freshness.resolve import Answer
from dep_freshness.tests.test_gradle_registry import CENTRAL, metadata
from dep_freshness.versions import exact_pin, google_api_key, newest_per_generation

V3_OLD = "v3-rev197-1.25.0"
V3_NEW = "v3-rev20260901-2.0.0"
V2 = "v2-rev20220709-2.0.0"


def test_the_key_is_generation_then_library_then_revision():
    assert google_api_key(V3_NEW)[0] == "v3"
    assert google_api_key(V3_NEW)[1] > google_api_key(V3_OLD)[1]
    assert google_api_key("v3-rev20260901-1.9.0")[1] < google_api_key(V3_OLD)[1]
    assert google_api_key("2.0.0") is None
    assert google_api_key("v3-rev197") is None


def test_newest_per_generation_keeps_every_generation():
    assert (
        newest_per_generation([V3_OLD, V2, V3_NEW, "junk", None, ""])
        == f"{V2} {V3_NEW}"
    )
    assert newest_per_generation(["1.0.0"]) is None
    # An older revision met AFTER the newest must not displace it.
    assert newest_per_generation([V3_NEW, V3_OLD]) == V3_NEW


def test_the_pin_keeps_its_generation_prefix():
    assert exact_pin(V3_OLD) == V3_OLD


def test_the_registry_answers_per_generation_when_nothing_else_parses(monkeypatch):
    name = "com.google.apis:google-api-services-drive"
    table = {maven.metadata_url(CENTRAL, name): metadata(V3_OLD, V2, V3_NEW)}
    monkeypatch.setattr(maven, "get_text", lambda url, *a, **k: table.get(url))
    assert maven.latest(name) == f"{V2} {V3_NEW}"


def dep(pinned: str = V3_OLD) -> Dep:
    return Dep(
        ecosystem="maven",
        name="com.google.apis:google-api-services-drive",
        constraint=pinned,
        path=Path("libs.versions.toml"),
        line=1,
        pinned=pinned,
    )


def test_a_pin_is_judged_inside_its_own_generation_only():
    finding = judge(dep(), Answer(f"{V2} {V3_NEW}"))
    assert finding.severity is Severity.STALE
    assert finding.latest == V3_NEW
    assert judge(dep(V3_NEW), Answer(f"{V2} {V3_NEW}")) is None


def test_a_generation_the_registry_dropped_is_unknown_not_a_pass():
    finding = judge(dep(), Answer(V2))
    assert finding.severity is Severity.UNKNOWN
    assert "v3 generation" in finding.detail
