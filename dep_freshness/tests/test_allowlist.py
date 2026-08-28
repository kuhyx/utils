"""Allowlist semantics: the two entry classes, and every way one can rot.

The split matters more than it looks. A `transitive:` entry is a predicate the
gate re-evaluates; a discretionary one is a promise with a date on it. Giving
a predicate entry an expiry date would turn the gate red on a calendar day for
a reason no commit can fix, which is why that combination is an error.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from dep_freshness.allowlist import AllowlistError, load
from dep_freshness.tests.conftest import write

NAME = "dependency-freshness.allowlist.yaml"


def _allowlist(root, body):
    return write(root, NAME, body)


TRANSITIVE = """\
exceptions:
  - ecosystem: pub
    package: plugin_platform_interface
    pinned: "2.1.8"
    latest_known: "2.2.0"
    reason: "firebase_core 4.2.0 constrains this below latest"
    blocked_by: "transitive:firebase_core@4.2.0"
"""


def _discretionary(days: int) -> str:
    when = date.today() + timedelta(days=days)
    return f"""\
exceptions:
  - ecosystem: pypi
    package: abandoned
    pinned: "1.4.0"
    reason: "upstream unmaintained"
    blocked_by: "https://github.com/kuhyx/x/issues/42"
    expires: "{when.isoformat()}"
"""


def test_no_allowlist_is_not_an_error(tmp_path):
    assert load(tmp_path) == []


def test_empty_allowlist_is_not_an_error(tmp_path):
    _allowlist(tmp_path, "")
    assert load(tmp_path) == []


def test_transitive_entry_parses_and_exposes_its_blocker(tmp_path):
    _allowlist(tmp_path, TRANSITIVE)
    entry = load(tmp_path)[0]
    assert entry.transitive
    assert entry.blocker == ("firebase_core", "4.2.0")
    assert entry.expires is None


def test_discretionary_entry_within_the_cap_is_accepted(tmp_path):
    _allowlist(tmp_path, _discretionary(30))
    entry = load(tmp_path)[0]
    assert not entry.transitive


def test_expired_discretionary_entry_is_an_error(tmp_path):
    _allowlist(tmp_path, _discretionary(-1))
    with pytest.raises(AllowlistError, match="expired"):
        load(tmp_path)


def test_an_expiry_beyond_ninety_days_is_an_error(tmp_path):
    _allowlist(tmp_path, _discretionary(120))
    with pytest.raises(AllowlistError, match="more than 90 days"):
        load(tmp_path)


def test_a_discretionary_entry_without_expires_is_an_error(tmp_path):
    _allowlist(tmp_path, """\
exceptions:
  - ecosystem: pypi
    package: abandoned
    pinned: "1.4.0"
    reason: "unmaintained"
    blocked_by: "discretionary"
""")
    with pytest.raises(AllowlistError, match="requires expires"):
        load(tmp_path)


def test_a_transitive_entry_may_not_carry_an_expiry(tmp_path):
    _allowlist(tmp_path, TRANSITIVE + '    expires: "2026-12-01"\n')
    with pytest.raises(AllowlistError, match="must NOT set expires"):
        load(tmp_path)


@pytest.mark.parametrize("field", ["ecosystem", "package", "pinned", "reason",
                                   "blocked_by"])
def test_every_required_field_is_required(tmp_path, field):
    # Blank the value rather than deleting the line: dropping `ecosystem:`
    # would also drop the `-` that makes the entry a list item, and the test
    # would then be asserting against a different error entirely.
    body = "\n".join(
        f"{line.split(field + ':')[0]}{field}: \"\"" if f"{field}:" in line else line
        for line in TRANSITIVE.splitlines()
    )
    _allowlist(tmp_path, body + "\n")
    with pytest.raises(AllowlistError, match="missing required field"):
        load(tmp_path)


def test_a_malformed_transitive_blocker_is_an_error(tmp_path):
    _allowlist(tmp_path, TRANSITIVE.replace(
        "transitive:firebase_core@4.2.0", "transitive:firebase_core"))
    with pytest.raises(AllowlistError, match="transitive:<package>@<version>"):
        load(tmp_path)


def test_a_bad_expiry_format_is_an_error(tmp_path):
    _allowlist(tmp_path, _discretionary(30).replace(
        (date.today() + __import__("datetime").timedelta(days=30)).isoformat(),
        "next tuesday"))
    with pytest.raises(AllowlistError, match="YYYY-MM-DD"):
        load(tmp_path)


def test_a_top_level_list_is_rejected(tmp_path):
    _allowlist(tmp_path, "- ecosystem: pub\n")
    with pytest.raises(AllowlistError, match="top-level 'exceptions:' list"):
        load(tmp_path)


def test_exceptions_must_be_a_list(tmp_path):
    _allowlist(tmp_path, "exceptions:\n  pub: nope\n")
    with pytest.raises(AllowlistError, match="must be a list"):
        load(tmp_path)


def test_an_entry_must_be_a_mapping(tmp_path):
    _allowlist(tmp_path, "exceptions:\n  - just-a-string\n")
    with pytest.raises(AllowlistError, match="must be a mapping"):
        load(tmp_path)


def test_unreadable_yaml_is_an_error(tmp_path):
    _allowlist(tmp_path, "exceptions: [\n")
    with pytest.raises(AllowlistError, match="unreadable"):
        load(tmp_path)


def test_the_shared_allowlist_is_inherited(tmp_path, no_shared_allowlist):
    """A fleet-wide blocker must not have to be copied into forty repos."""
    no_shared_allowlist.write_text(TRANSITIVE, encoding="utf-8")
    entries = load(tmp_path)
    assert [(e.ecosystem, e.package) for e in entries] == [
        ("pub", "plugin_platform_interface")
    ]


def test_a_repo_entry_overrides_the_shared_one(tmp_path, no_shared_allowlist):
    no_shared_allowlist.write_text(TRANSITIVE, encoding="utf-8")
    _allowlist(tmp_path, TRANSITIVE.replace(
        'reason: "firebase_core 4.2.0 constrains this below latest"',
        'reason: "this repo has its own reason"'))
    entries = load(tmp_path)
    assert len(entries) == 1
    assert entries[0].reason == "this repo has its own reason"


def test_shared_and_repo_entries_for_different_packages_both_apply(
    tmp_path, no_shared_allowlist
):
    no_shared_allowlist.write_text(TRANSITIVE, encoding="utf-8")
    _allowlist(tmp_path, _discretionary(30))
    assert {e.package for e in load(tmp_path)} == {
        "plugin_platform_interface", "abandoned"
    }


def test_a_malformed_shared_allowlist_is_an_error(tmp_path, no_shared_allowlist):
    no_shared_allowlist.write_text("exceptions:\n  - just-a-string\n",
                                   encoding="utf-8")
    with pytest.raises(AllowlistError, match="must be a mapping"):
        load(tmp_path)


def test_the_shared_path_defaults_to_the_gate_repo(monkeypatch):
    from dep_freshness.allowlist import shared_path
    monkeypatch.delenv("DEP_FRESHNESS_SHARED_ALLOWLIST", raising=False)
    assert shared_path().name == NAME
    assert shared_path().parent.name == "utils"
