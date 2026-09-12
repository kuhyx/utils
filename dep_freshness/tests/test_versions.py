"""The fail-green class: a pre-release accepted as latest stable."""

from __future__ import annotations

import pytest

from dep_freshness.versions import (
    behind,
    exact_pin,
    is_prerelease,
    newest_stable,
    reference,
    split_tag_prefix,
)


@pytest.mark.parametrize("raw", [
    "2.0.0-beta.1", "1.0.0-rc1", "3.0.0-dev.4", "2.0.0rc1", "1.2.3a1",
    "v4.0.0-alpha", "1.0.0.dev3",
])
def test_prereleases_are_recognised(raw):
    assert is_prerelease(raw)


@pytest.mark.parametrize("raw", ["1.0.0", "10.3.0", "v2.1.5", "0.14.4", "1.6.0+1"])
def test_stable_versions_are_not_prereleases(raw):
    assert not is_prerelease(raw)


def test_newest_stable_skips_prereleases():
    assert newest_stable(["1.0.0", "2.0.0-beta.1", "1.9.3"]) == "1.9.3"


def test_newest_stable_is_none_when_everything_is_a_prerelease():
    assert newest_stable(["1.0.0-a", "2.0.0-b"]) is None


def test_newest_stable_ignores_unparseable_entries():
    assert newest_stable(["not-a-version", "", None, "1.2.0"]) == "1.2.0"


@pytest.mark.parametrize("raw,expected", [
    ("1.6.0", "1.6.0"), ("==1.6.0", "1.6.0"), ("v2.0.0", "2.0.0"),
    ("  1.0.0  ", "1.0.0"), ("1.9", "1.9"), ("3", "3"),
    # PyPI stub packages date-stamp a fourth component. Capping the regex at
    # three reported this exact pin as unpinned *against its own value*.
    ("==2.33.0.20260712", "2.33.0.20260712"),
])
def test_exact_pins_are_recognised(raw, expected):
    assert exact_pin(raw) == expected


@pytest.mark.parametrize("raw", ["^1.6.0", ">=1.6.0", "any", "*", "", ">=1,<2", "~1.2"])
def test_ranges_are_not_exact_pins(raw):
    assert exact_pin(raw) is None


def test_behind_compares_versions():
    assert behind("1.6.0", "1.7.0")
    assert not behind("1.7.0", "1.7.0")
    assert not behind("1.8.0", "1.7.0")


def test_behind_never_fires_on_unparseable_input():
    """An unpinned constraint is UNPINNED, never dressed up as staleness."""
    assert not behind("^1.6.0", "1.7.0")
    assert not behind("1.6.0", "latest")


@pytest.mark.parametrize("raw,expected", [
    ("natural-comparator-1.1", ("natural-comparator-", "1.1")),
    ("release-v2.0", ("release-", "v2.0")),
    ("2.3.0-rc1", ("", "2.3.0-rc1")),
    ("v1.0.0", ("", "v1.0.0")),
    ("alpha", ("", "alpha")),
])
def test_a_project_named_tag_splits_into_prefix_and_version(raw, expected):
    """JitPack serves java-nat-sort only as `natural-comparator-1.1`."""
    assert split_tag_prefix(raw) == expected


def test_a_project_named_tag_is_a_stable_version_with_its_prefix_kept():
    assert not is_prerelease("natural-comparator-1.1")
    assert is_prerelease("natural-comparator-1.2-rc1")
    assert newest_stable(["natural-comparator-1.1", "natural-comparator-1.0"]) == (
        "natural-comparator-1.1"
    )
    assert behind("natural-comparator-1.0", "natural-comparator-1.1")
    assert exact_pin("natural-comparator-1.1") == "natural-comparator-1.1"
    assert exact_pin("version-v1.2") == "version-1.2"


def test_reference_is_newest_stable_when_one_exists():
    assert reference(["1.0.0", "2.0.0-alpha01"]) == "1.0.0"


def test_reference_falls_back_to_newest_prerelease_only_when_nothing_is_stable():
    """androidx.biometric:biometric-ktx: alpha-only since 2021."""
    assert reference(["1.2.0-alpha05", "1.4.0-alpha02", "1.3.0-alpha01"]) == "1.4.0-alpha02"
    assert reference(iter(["1.4.0-alpha02", "junk"])) == "1.4.0-alpha02"
    assert reference([]) is None
    assert reference(["junk", ""]) is None


def test_an_api_generation_is_not_a_project_name():
    """Google's `v3-rev197-1.25.0`: splitting on `v3-rev197-` compared the
    Drive v3 client against a v2 artifact and called v2 newer."""
    assert split_tag_prefix("v3-rev197-1.25.0") == ("", "v3-rev197-1.25.0")
    assert is_prerelease("v3-rev197-1.25.0")
    assert newest_stable(["v3-rev197-1.25.0", "v2-rev20220709-2.0.0"]) is None
    # ... and the no-stable fallback must not pick one up either: loosely
    # parsed, every v3 revision is "3" and the 2019 pin reads as current.
    assert reference(["v3-rev197-1.25.0", "v3-rev20250723-2.0.0"]) is None
