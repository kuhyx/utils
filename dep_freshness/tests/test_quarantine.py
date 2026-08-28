"""pnpm 11 refuses freshly-published packages; the gate must agree.

Reporting a repo as behind a version its package manager will not install is a
finding nobody can act on -- the pre-commit hook would fail, and the fix the
message asks for would fail too.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from dep_freshness import check, quarantine
from dep_freshness.models import Dep, Finding, Severity
from dep_freshness.tests.conftest import write

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


def _stamp(hours_ago: float) -> str:
    return (NOW - timedelta(hours=hours_ago)).isoformat().replace("+00:00", "Z")


PACKUMENT = {
    "time": {
        "created": _stamp(9000),
        "modified": _stamp(1),
        "16.3.0": _stamp(900),
        "16.3.2": _stamp(400),
        "16.3.3": _stamp(18),      # inside the 24h window
    }
}


@pytest.fixture
def packument(monkeypatch):
    def install(payload):
        monkeypatch.setattr(quarantine, "get_json", lambda *_a, **_k: payload)
    return install


def test_a_release_inside_the_window_is_not_installable(packument):
    packument(PACKUMENT)
    assert quarantine.installable_latest("x", "16.3.3", now=NOW) == "16.3.2"


def test_a_release_outside_the_window_is_installable(packument):
    packument(PACKUMENT)
    assert quarantine.installable_latest("x", "16.3.2", now=NOW) == "16.3.2"


def test_versions_above_the_dist_tag_are_ignored(packument):
    """npm lets a maintenance release outrank `latest` numerically."""
    payload = {"time": {**PACKUMENT["time"], "17.0.0": _stamp(500)}}
    packument(payload)
    assert quarantine.installable_latest("x", "16.3.3", now=NOW) == "16.3.2"


def test_the_created_and_modified_keys_are_not_versions(packument):
    packument({"time": {"created": _stamp(900), "modified": _stamp(1)}})
    assert quarantine.installable_latest("x", "1.0.0", now=NOW) is None


def test_an_unparseable_timestamp_is_skipped(packument):
    packument({"time": {"1.0.0": "not a date", "0.9.0": _stamp(500)}})
    assert quarantine.installable_latest("x", "1.0.0", now=NOW) == "0.9.0"


def test_an_unparseable_ceiling_stops_narrowing_but_the_window_still_applies(
    packument,
):
    packument(PACKUMENT)
    # No version ceiling to apply, but 16.3.3 is still 18h old.
    assert quarantine.installable_latest("x", "latest", now=NOW) == "16.3.2"


def test_a_registry_without_a_time_map_is_undeterminable(packument):
    packument({"versions": {"1.0.0": {}}})
    assert quarantine.installable_latest("x", "1.0.0", now=NOW) is None


def test_a_missing_package_is_undeterminable(packument):
    packument(None)
    assert quarantine.installable_latest("x", "1.0.0", now=NOW) is None


def test_offline_is_undeterminable(monkeypatch):
    from dep_freshness.registries.http import Offline

    def down(*_a, **_k):
        raise Offline("no network")

    monkeypatch.setattr(quarantine, "get_json", down)
    assert quarantine.installable_latest("x", "1.0.0") is None


def test_the_cutoff_defaults_to_now():
    assert quarantine.cutoff() < datetime.now(timezone.utc)


def _dep(ecosystem="npm", pinned="16.3.2", constraint="16.3.2") -> Dep:
    from pathlib import Path
    return Dep(ecosystem=ecosystem, name="@testing-library/react",
               constraint=constraint, path=Path("package.json"), line=1,
               pinned=pinned)


def test_a_finding_only_caused_by_a_quarantined_release_is_dropped(monkeypatch):
    monkeypatch.setattr(check, "installable_latest",
                        lambda _n, _c: "16.3.2")
    finding = Finding(_dep(), Severity.STALE, "16.3.3")
    assert check._unquarantine(finding) is None


def test_a_finding_that_survives_the_narrowing_is_kept(monkeypatch):
    monkeypatch.setattr(check, "installable_latest", lambda _n, _c: "16.3.2")
    finding = Finding(_dep(pinned="16.1.0"), Severity.STALE, "16.3.3")
    survivor = check._unquarantine(finding)
    assert survivor is not None
    assert survivor.latest == "16.3.2"


def test_non_npm_findings_are_never_narrowed(monkeypatch):
    monkeypatch.setattr(check, "installable_latest", _explode)
    finding = Finding(_dep(ecosystem="pub"), Severity.STALE, "1.0.0")
    assert check._unquarantine(finding) is finding


def test_a_finding_with_no_latest_is_never_narrowed(monkeypatch):
    monkeypatch.setattr(check, "installable_latest", _explode)
    finding = Finding(_dep(), Severity.UNKNOWN, None)
    assert check._unquarantine(finding) is finding


def test_an_undeterminable_narrowing_leaves_the_finding_alone(monkeypatch):
    monkeypatch.setattr(check, "installable_latest", lambda _n, _c: None)
    finding = Finding(_dep(pinned="16.1.0"), Severity.STALE, "16.3.3")
    assert check._unquarantine(finding) is finding


def test_a_clean_run_never_pays_for_the_full_document(repo, monkeypatch,
                                                      cache_dir):
    """The full packument is 7MB for react; it must not be fetched when
    everything is already current."""
    monkeypatch.setattr(check, "installable_latest", _explode)
    monkeypatch.setattr("dep_freshness.resolve._fetch",
                        lambda _e, _n: "19.2.8")
    write(repo, "package.json", '{"dependencies": {"react": "19.2.8"}}')
    monkeypatch.chdir(repo)
    assert check.main(["--all"]) == 0


def _explode(*_args):
    raise AssertionError("the full packument must not be fetched here")


def test_a_repo_pinned_to_the_newest_installable_version_passes(
    repo, monkeypatch, cache_dir
):
    """End to end: the only finding is a release pnpm would refuse, so the
    gate must exit 0 rather than demand a version that cannot be installed."""
    monkeypatch.setattr("dep_freshness.resolve._fetch", lambda _e, _n: "16.3.3")
    monkeypatch.setattr(check, "installable_latest", lambda _n, _c: "16.3.2")
    write(repo, "package.json",
          '{"dependencies": {"@testing-library/react": "16.3.2"}}')
    monkeypatch.chdir(repo)
    assert check.main(["--all"]) == 0
