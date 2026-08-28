"""Allowlist behaviour, end to end: what an exception excuses, and when it rots.

Split out of test_check.py for the 250-line cap. The fixtures (`run`,
`canned`, `repo`, and the `no_shared_allowlist` redirect) live in conftest.py
so both files see one definition.
"""

from __future__ import annotations

from datetime import date, timedelta

from dep_freshness.tests.conftest import (
    ALLOWLIST,
    CURRENT_PUBSPEC,
    STALE_PUBSPEC,
    write,
)

SHARED = """\
exceptions:
  - ecosystem: pub
    package: some_other_package
    pinned: "1.0.0"
    reason: "a fleet-wide hold on something this repo does not use"
    blocked_by: "transitive:whatever@1.0.0"
"""


def test_a_transitive_exception_excuses_the_finding(repo, run):
    write(repo, "pubspec.yaml", STALE_PUBSPEC)
    write(repo, ALLOWLIST, """\
exceptions:
  - ecosystem: pub
    package: http
    pinned: "1.5.0"
    reason: "something upstream holds it"
    blocked_by: "transitive:some_pkg@1.0.0"
""")
    assert run("--all") == 0


def test_an_exception_prints_loudly_even_on_success(repo, run, capsys):
    test_a_transitive_exception_excuses_the_finding(repo, run)
    err = capsys.readouterr().err
    assert "DEPENDENCY EXCEPTION IN USE" in err
    assert "still blocking" in err


def test_an_exception_with_nothing_left_to_excuse_is_an_error(repo, run, capsys):
    write(repo, "pubspec.yaml", CURRENT_PUBSPEC)
    write(repo, ALLOWLIST, """\
exceptions:
  - ecosystem: pub
    package: http
    pinned: "1.5.0"
    reason: "stale entry nobody removed"
    blocked_by: "transitive:some_pkg@1.0.0"
""")
    assert run("--all") == 2
    assert "no longer stale" in capsys.readouterr().err


def test_a_file_scoped_run_never_judges_an_entry_dead(repo, run, capsys):
    """pre-commit passes staged files, so it only ever sees a subset.

    The entry below excuses a dependency that lives in a manifest outside the
    scoped path. `--all` would find it stale and mark the entry used; a scoped
    run cannot, and must not conclude the entry is rot -- that failed a commit
    in utils over the fleet-wide typescript hold when the staged files were
    two pubspec.yaml.
    """
    write(repo, "pubspec.yaml", STALE_PUBSPEC)
    write(repo, "sub/pubspec.yaml", CURRENT_PUBSPEC)
    write(repo, ALLOWLIST, """\
exceptions:
  - ecosystem: pub
    package: http
    pinned: "1.5.0"
    reason: "held by something upstream"
    blocked_by: "transitive:some_pkg@1.0.0"
""")
    assert run("sub/pubspec.yaml") == 0
    assert "no longer stale" not in capsys.readouterr().err
    # The same allowlist over the whole repo still excuses, not rots.
    assert run("--all") == 0


def test_an_expired_allowlist_exits_two(repo, run, capsys):
    write(repo, "pubspec.yaml", STALE_PUBSPEC)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    write(repo, ALLOWLIST, f"""\
exceptions:
  - ecosystem: pub
    package: http
    pinned: "1.5.0"
    reason: "held"
    blocked_by: "discretionary"
    expires: "{yesterday}"
""")
    assert run("--all") == 2
    assert "Allowlist ERROR" in capsys.readouterr().err


def test_an_inherited_entry_this_repo_does_not_need_is_not_rot(
    repo, run, no_shared_allowlist
):
    """A fleet-wide hold on typescript excuses nothing in a Flutter app.

    Treating that as a dead entry would make every repo without the dependency
    uncommittable -- the shared allowlist would be unusable for the exact case
    it exists for.
    """
    no_shared_allowlist.write_text(SHARED, encoding="utf-8")
    write(repo, "pubspec.yaml", CURRENT_PUBSPEC)
    assert run("--all") == 0


def test_a_repo_local_entry_with_nothing_to_excuse_is_still_rot(
    repo, run, no_shared_allowlist
):
    no_shared_allowlist.write_text(SHARED, encoding="utf-8")
    write(repo, "pubspec.yaml", CURRENT_PUBSPEC)
    write(repo, ALLOWLIST, """\
exceptions:
  - ecosystem: pub
    package: http
    pinned: "1.5.0"
    reason: "this repo's own stale entry"
    blocked_by: "transitive:x@1.0.0"
""")
    assert run("--all") == 2


def test_an_exception_excuses_only_the_version_it_names(repo, run, capsys):
    """A held version is an argument about ONE version, not a blank cheque.

    The fleet-wide typescript entry pins 6.0.3 with a reason specific to it;
    dufs-cloud/web sat on `~5.8.3`, two majors older for no stated reason, and
    the gate reported it current because the label matched.
    """
    write(repo, "pubspec.yaml", STALE_PUBSPEC.replace("1.5.0", "1.4.0"))
    write(repo, ALLOWLIST, """\
exceptions:
  - ecosystem: pub
    package: http
    pinned: "1.5.0"
    reason: "1.5.0 is held; 1.4.0 is not"
    blocked_by: "transitive:some_pkg@1.0.0"
""")
    assert run("--all") == 1
    assert "pub:http" in capsys.readouterr().err
