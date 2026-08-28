"""Range arithmetic. Wrong here means red for a reason no commit can fix."""

from __future__ import annotations

import pytest

from dep_freshness.constraints import _upper_for_caret, lower_bound, satisfies


@pytest.mark.parametrize("constraint,version,expected", [
    ("^3.12.2", "3.13.2", True),
    ("^3.12.2", "4.0.0", False),
    ("^3.12.2", "3.12.1", False),
    ("^0.2.1", "0.3.0", False),      # caret's 0.x special case
    ("^0.2.1", "0.2.9", True),
    ("^0.0.3", "0.0.4", False),
    ("~1.2.0", "1.2.9", True),
    ("~1.2.0", "1.3.0", False),
    ("~>2.1.0", "2.1.5", True),
    (">=3.8.0 <4.0.0", "3.13.2", True),
    (">=3.8,<3.13", "3.14.7", False),
    (">3.0.0", "3.0.0", False),
    ("<=2.0.0", "2.0.0", True),
    ("!=1.5.0", "1.5.0", False),
    ("==1.6.0", "1.6.0", True),
    ("1.6.0", "1.7.0", False),
    ("any", "9.9.9", True),
    ("*", "9.9.9", True),
    ("", "9.9.9", True),
])
def test_satisfies(constraint, version, expected):
    assert satisfies(constraint, version) is expected


def test_an_unparseable_candidate_is_never_a_violation():
    assert satisfies("^1.0.0", "not-a-version")


def test_a_constraint_with_no_version_at_all_admits_everything():
    assert satisfies("workspace", "1.0.0")


def test_an_unparseable_bound_is_ignored_rather_than_failing():
    assert satisfies(">=abc", "1.0.0")


def test_quoted_constraints_are_unwrapped():
    assert satisfies('">=3.8.0 <4.0.0"', "3.13.2")


@pytest.mark.parametrize("text,expected", [
    ("1.2.3", "2.0.0"), ("0.2.1", "0.3.0"), ("0.0.3", "0.0.4"), ("2", "3.0.0"),
])
def test_caret_upper_bounds(text, expected):
    assert _upper_for_caret(text) == expected


@pytest.mark.parametrize("constraint,expected", [
    ("^10.2.0", "10.2.0"), (">=1.2", "1.2"), ("==3.0.0", "3.0.0"),
    ("~1.4.0", "1.4.0"), ("2.0.0", "2.0.0"), ("any", None), ("", None),
])
def test_lower_bound(constraint, expected):
    assert lower_bound(constraint) == expected
