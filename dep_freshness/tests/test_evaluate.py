"""The rules: when does the gate object, and when must it stay quiet?

The quiet cases are the ones worth testing. A gate that fires on `sdk: ^3.12.2`
because Dart shipped 3.13.2 -- a version that constraint already permits -- is
a gate the user turns off.
"""

from __future__ import annotations

from pathlib import Path

from dep_freshness.evaluate import judge
from dep_freshness.models import Dep, Severity
from dep_freshness.resolve import Answer


def dep(**kwargs) -> Dep:
    base = {"ecosystem": "pub", "name": "http", "constraint": "1.6.0",
            "path": Path("pubspec.yaml"), "line": 1, "pinned": "1.6.0"}
    return Dep(**{**base, **kwargs})


def test_a_current_exact_pin_passes():
    assert judge(dep(), Answer("1.6.0")) is None


def test_a_stale_exact_pin_is_reported():
    finding = judge(dep(), Answer("1.7.0"))
    assert finding.severity is Severity.STALE
    assert finding.latest == "1.7.0"


def test_a_range_is_reported_unpinned_with_the_version_to_use():
    finding = judge(dep(constraint="^1.6.0", pinned=None), Answer("1.7.0"))
    assert finding.severity is Severity.UNPINNED
    assert "1.7.0" in finding.detail


def test_an_unconstrained_dependency_is_reported_unpinned():
    """`plugin_platform_interface: any` -- the one Phase-0 pub anomaly."""
    finding = judge(dep(constraint="any", pinned=None), Answer("2.2.0"))
    assert finding.severity is Severity.UNPINNED


def test_a_lockfile_disagreeing_with_the_manifest_is_reported():
    finding = judge(dep(locked="1.5.0"), Answer("1.6.0"))
    assert finding.severity is Severity.LOCK_MISMATCH
    assert "1.5.0" in finding.detail


def test_a_missing_lockfile_is_not_a_violation():
    assert judge(dep(locked=None), Answer("1.6.0")) is None


def test_an_override_is_always_reported():
    assert judge(dep(override=True), Answer("1.6.0")).severity is Severity.OVERRIDE


def test_a_caret_allowed_package_passes_at_the_current_floor():
    assert judge(
        dep(name="very_good_analysis", constraint="^10.3.0", pinned=None,
            caret_ok=True),
        Answer("10.3.0"),
    ) is None


def test_a_caret_allowed_package_is_stale_when_its_floor_is_behind():
    finding = judge(
        dep(name="very_good_analysis", constraint="^10.2.0", pinned=None,
            caret_ok=True),
        Answer("10.3.0"),
    )
    assert finding.severity is Severity.STALE
    assert "floor 10.2.0" in finding.detail


def test_a_toolchain_range_that_admits_the_current_version_passes():
    assert judge(
        dep(ecosystem="toolchain", name="dart", constraint="^3.12.2",
            pinned=None, caret_ok=True),
        Answer("3.13.2"),
    ) is None


def test_a_toolchain_range_that_excludes_the_current_version_fails():
    finding = judge(
        dep(ecosystem="toolchain", name="python", constraint=">=3.8,<3.13",
            pinned=None, caret_ok=True),
        Answer("3.14.7"),
    )
    assert finding.severity is Severity.STALE
    assert "excludes the current toolchain" in finding.detail


def test_a_channel_name_in_fvmrc_is_reported_unpinned():
    finding = judge(
        dep(ecosystem="toolchain", name="flutter", constraint="stable",
            pinned=None),
        Answer("3.47.2"),
    )
    assert finding.severity is Severity.UNPINNED


def test_a_pinned_toolchain_behind_latest_is_stale():
    finding = judge(
        dep(ecosystem="toolchain", name="flutter", constraint="3.47.1",
            pinned="3.47.1"),
        Answer("3.47.2"),
    )
    assert finding.severity is Severity.STALE


def test_no_answer_at_all_is_unknown_not_stale():
    finding = judge(dep(), Answer(None, unavailable=True))
    assert finding.severity is Severity.UNKNOWN


def test_a_package_with_no_stable_release_is_unknown():
    finding = judge(dep(), Answer(None))
    assert finding.severity is Severity.UNKNOWN
    assert "no stable release" in finding.detail
