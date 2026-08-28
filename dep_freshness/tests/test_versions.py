"""The fail-green class: a pre-release accepted as latest stable."""

from __future__ import annotations

import pytest

from dep_freshness.versions import behind, exact_pin, is_prerelease, newest_stable


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
    ("  1.0.0  ", "1.0.0"),
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
