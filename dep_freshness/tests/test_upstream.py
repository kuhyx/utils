"""The `upstream:` predicate: an entry holds while the fork's upstream agrees.

The rot case is the one that matters: the day upstream bumps, the entry must
die loudly rather than keep excusing a pin nobody is waiting on any more.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dep_freshness import upstream
from dep_freshness.allowlist import AllowlistError, load
from dep_freshness.models import Dep, Exception_, Finding, Severity
from dep_freshness.registries.http import Offline
from dep_freshness.report import exceptions_block, machine_lines
from dep_freshness.tests.conftest import ALLOWLIST, STALE_PUBSPEC, write

UPSTREAM_ENTRY = """\
exceptions:
  - ecosystem: pub
    package: http
    pinned: "1.5.0"
    reason: "the project we fork from is still on 1.5.0"
    blocked_by: "upstream:someone/demo"
"""


def entry(**kwargs) -> Exception_:
    base = {
        "ecosystem": "pub",
        "package": "http",
        "pinned": "1.5.0",
        "reason": "r",
        "blocked_by": "upstream:someone/demo",
    }
    return Exception_(**{**base, **kwargs})


def finding(root: Path, path: str = "pubspec.yaml") -> Finding:
    dep = Dep(
        ecosystem="pub",
        name="http",
        constraint="1.5.0",
        path=root / path,
        line=5,
        pinned="1.5.0",
    )
    return Finding(dep, Severity.STALE, "1.6.0")


@pytest.fixture
def raw(monkeypatch):
    """Canned bodies per raw.githubusercontent URL; anything else is a 404."""
    table: dict[str, str] = {}
    monkeypatch.setattr(upstream, "get_text", lambda url, *a, **k: table.get(url))
    return table


URL = "https://raw.githubusercontent.com/someone/demo/HEAD/pubspec.yaml"


def test_the_upstream_manifest_is_fetched_at_the_same_relative_path(raw, tmp_path):
    raw[URL] = STALE_PUBSPEC
    assert upstream.upstream_pin(entry(), finding(tmp_path), tmp_path) == "1.5.0"
    assert upstream.still_pins(entry(), finding(tmp_path), tmp_path)


def test_upstream_having_moved_on_clears_the_entry(raw, tmp_path):
    raw[URL] = STALE_PUBSPEC.replace("1.5.0", "1.6.0")
    assert not upstream.still_pins(entry(), finding(tmp_path), tmp_path)


def test_no_upstream_manifest_or_no_such_package_is_no_pin(raw, tmp_path):
    assert upstream.upstream_pin(entry(), finding(tmp_path), tmp_path) is None
    raw[URL] = "name: demo\ndependencies:\n  other: 1.0.0\n"
    assert upstream.upstream_pin(entry(), finding(tmp_path), tmp_path) is None


def test_a_manifest_outside_the_repo_is_no_pin(raw, tmp_path):
    outside = finding(tmp_path.parent, "elsewhere/pubspec.yaml")
    assert upstream.upstream_pin(entry(), outside, tmp_path / "repo") is None


def test_offline_propagates_from_the_transport(monkeypatch, tmp_path):
    def down(*_a, **_k):
        raise Offline("down")

    monkeypatch.setattr(upstream, "get_text", down)
    with pytest.raises(Offline):
        upstream.still_pins(entry(), finding(tmp_path), tmp_path)


def test_an_upstream_entry_parses_and_may_not_carry_an_expiry(tmp_path):
    write(tmp_path, ALLOWLIST, UPSTREAM_ENTRY)
    parsed = load(tmp_path)[0]
    assert parsed.upstream and parsed.predicate and not parsed.transitive
    assert parsed.upstream_repo == "someone/demo"
    assert parsed.blocker is None
    write(tmp_path, ALLOWLIST, UPSTREAM_ENTRY + '    expires: "2099-01-01"\n')
    with pytest.raises(AllowlistError, match="must NOT set expires"):
        load(tmp_path)


def test_an_upstream_entry_must_name_owner_slash_repo(tmp_path):
    write(tmp_path, ALLOWLIST, UPSTREAM_ENTRY.replace("someone/demo", "demo"))
    with pytest.raises(AllowlistError, match="upstream:<owner>/<repo>"):
        load(tmp_path)


def test_the_report_treats_it_as_a_predicate(capsys):
    exceptions_block([entry()], {"pub:http": False})
    assert "CLEARED" in capsys.readouterr().err
    assert "[still blocking]" in machine_lines([entry()])[0]


def test_end_to_end_the_entry_excuses_while_upstream_agrees(repo, run, raw):
    raw[URL] = STALE_PUBSPEC
    write(repo, "pubspec.yaml", STALE_PUBSPEC)
    write(repo, ALLOWLIST, UPSTREAM_ENTRY)
    assert run("--all", "--strict") == 0


def test_end_to_end_upstream_moving_on_fails_the_pin(repo, run, raw, capsys):
    raw[URL] = STALE_PUBSPEC.replace("1.5.0", "1.6.0")
    write(repo, "pubspec.yaml", STALE_PUBSPEC)
    write(repo, ALLOWLIST, UPSTREAM_ENTRY)
    assert run("--all", "--strict") == 1
    err = capsys.readouterr().err
    assert "no longer pins 1.5.0" in err
    assert "CLEARED" in err


def test_end_to_end_offline_trusts_the_entry_but_degrades(
    repo, run, monkeypatch, capsys
):
    def down(*_a, **_k):
        raise Offline("down")

    monkeypatch.setattr(upstream, "get_text", down)
    write(repo, "pubspec.yaml", STALE_PUBSPEC)
    write(repo, ALLOWLIST, UPSTREAM_ENTRY)
    assert run("--all") == 0
    assert "upstream:someone/demo unverified" in capsys.readouterr().err
    assert run("--all", "--strict") == 3


def test_a_transitive_entry_has_no_upstream_repo():
    assert entry(blocked_by="transitive:x@1.0.0").upstream_repo is None


def test_offline_without_a_degraded_list_still_trusts_the_entry(monkeypatch, tmp_path):
    from dep_freshness.check import _upstream_holds

    def down(*_a, **_k):
        raise Offline("down")

    monkeypatch.setattr(upstream, "get_text", down)
    assert _upstream_holds(entry(), finding(tmp_path), tmp_path, None)
