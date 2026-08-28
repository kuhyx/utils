"""The remaining branches: defensive paths, and output shapes.

These are the lines a happy-path suite never reaches -- a corrupt input, a
missing binary, the discretionary half of a report block. They are exactly
where a gate quietly stops gating, so they are covered deliberately.
"""

from __future__ import annotations

from datetime import date, timedelta
import io
from pathlib import Path
import subprocess

import pytest

from dep_freshness import check, discover, report, resolve
from dep_freshness.allowlist import _parse_date, load
from dep_freshness.models import Dep, Exception_, Finding, Severity
from dep_freshness.registries import cargo, gomod, pub, pypi
from dep_freshness.registries.http import Offline
from dep_freshness.tests.conftest import write
from dep_freshness.versions import newest_stable, parse


def test_yaml_parses_an_unquoted_date_natively():
    """`expires: 2026-10-15` without quotes arrives as a `datetime.date`."""
    when = date(2026, 10, 15)
    assert _parse_date(when, "x") == when


def test_an_unquoted_expiry_in_yaml_is_accepted(tmp_path):
    when = (date.today() + timedelta(days=10)).isoformat()
    write(tmp_path, "dependency-freshness.allowlist.yaml", f"""\
exceptions:
  - ecosystem: pypi
    package: x
    pinned: "1.0.0"
    reason: "held"
    blocked_by: "discretionary"
    expires: {when}
""")
    assert load(tmp_path)[0].expires == when


def test_a_discretionary_entry_has_no_blocker_tuple():
    entry = Exception_("pypi", "x", "1.0.0", "r", "discretionary", expires="2026-10-15")
    assert entry.blocker is None


@pytest.mark.parametrize("module", [cargo, gomod, pub, pypi])
def test_a_missing_package_is_none_everywhere(monkeypatch, module):
    monkeypatch.setattr(module, "get_json", lambda *_a, **_k: None)
    assert module.latest("nope") is None


def test_pypi_matches_a_version_inside_a_hyphenated_filename(monkeypatch):
    monkeypatch.setattr(pypi, "get_json", lambda *_a, **_k: {
        "versions": ["1.0.0"],
        "files": [{"filename": "my-pkg-1.0.0-py3-none-any.whl", "yanked": False}],
    })
    assert pypi.latest("my-pkg") == "1.0.0"


def test_pypi_ignores_a_file_whose_version_it_cannot_place(monkeypatch):
    monkeypatch.setattr(pypi, "get_json", lambda *_a, **_k: {
        "versions": ["1.0.0"],
        "files": [{"filename": "junk.txt", "yanked": False}],
    })
    assert pypi.latest("pkg") == "1.0.0"


def test_a_semver_prerelease_that_pep440_rejects_still_parses():
    assert parse("1.2.3-a.b.c") == parse("1.2.3")


def test_a_string_that_is_no_kind_of_version_does_not_parse():
    assert parse("stable") is None
    assert parse("1.2.3.4.5-!!!") is None


def test_newest_stable_ignores_a_lower_candidate():
    assert newest_stable(["2.0.0", "1.0.0"]) == "2.0.0"


def test_a_constraint_bound_that_will_not_parse_is_permissive():
    from dep_freshness.constraints import _clause
    assert _clause(">=", "not-a-version", parse("1.0.0"))


def test_a_toolchain_pin_at_latest_passes():
    from dep_freshness.evaluate import judge
    dep = Dep(ecosystem="toolchain", name="flutter", constraint="3.47.2",
              path=Path(".fvmrc"), line=1, pinned="3.47.2")
    assert judge(dep, resolve.Answer("3.47.2")) is None
