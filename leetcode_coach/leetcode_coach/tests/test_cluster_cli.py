"""Tests for `leetcode due`, `leetcode --cluster <name>` and `leetcode --retest <slug>`.

The prints are the interface (T201 exemption), so these assert on stdout.
"""

from __future__ import annotations

import datetime as dt
import os
from typing import TYPE_CHECKING

import pytest

from leetcode_coach import cluster_cli, leetcode_repl, local_session, progress
from leetcode_coach.tests.test_progress import log, solve
from leetcode_guard import _leetcode, _live_solved

if TYPE_CHECKING:
    from pathlib import Path

TODAY = progress.local_today()


@pytest.fixture
def sessions(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv(progress.SESSIONS_ENV, str(tmp_path))
    monkeypatch.delenv(progress.CLUSTER_ENV, raising=False)
    return tmp_path


class Starter:
    """Stands in for the coaching session; may log a post-mortem like kuhy would."""

    def __init__(self, directory: Path, *, postmortem: bool = True) -> None:
        self.directory, self.postmortem = directory, postmortem
        self.problems: list[list[str]] = []
        self.cluster: str | None = None

    def __call__(self, problem: list[str]) -> int:
        self.problems.append(problem)
        self.cluster = os.environ.get(progress.CLUSTER_ENV)
        if self.postmortem:
            log(self.directory, TODAY, problem[0], {"event": "postmortem"})
        return 0


def never(_slug: str) -> bool:
    return False


def test_due_lists_nothing(sessions: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cluster_cli.main(["due"], Starter(sessions)) == 0
    assert capsys.readouterr().out == "no re-tests due\n"


def test_due_lists_a_three_day_retest(
    sessions: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    solve(sessions, TODAY - dt.timedelta(days=3), "missing-number")
    assert cluster_cli.main(["due"], Starter(sessions)) == 0
    out = capsys.readouterr().out
    assert "missing-number" in out
    assert "re-test 1/2" in out
    assert "bit-cancellation" in out
    assert "leetcode --retest missing-number" in out


def test_cluster_serves_the_next_unstarted_problem(
    sessions: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    solve(sessions, TODAY, "missing-number")
    start = Starter(sessions, postmortem=False)
    assert cluster_cli.main(["--cluster", "bit-cancellation"], start, never) == 0
    assert start.problems == [["single-number-iii"]]
    assert start.cluster == "bit-cancellation"
    assert "next in bit-cancellation: single-number-iii (#260)" in (
        capsys.readouterr().out
    )


def test_cluster_skips_a_problem_accepted_on_leetcode(sessions: Path) -> None:
    start = Starter(sessions, postmortem=False)
    accepted = {"missing-number"}.__contains__
    assert cluster_cli.main(["--cluster", "bit-cancellation"], start, accepted) == 0
    assert start.problems == [["single-number-iii"]]


def test_cluster_serves_a_due_retest_first(
    sessions: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    solve(sessions, TODAY - dt.timedelta(days=3), "single-number-iii")
    solve(sessions, TODAY - dt.timedelta(days=3), "two-sum")
    start = Starter(sessions)
    assert cluster_cli.main(["--cluster", "bit-cancellation"], start, never) == 0
    assert start.problems[0][0] == "single-number-iii"
    assert start.problems[0][1].startswith(cluster_cli.COLD_RETEST_TAG)
    assert "re-test due: single-number-iii" in capsys.readouterr().out


def test_dry_run_starts_nothing(
    sessions: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    solve(sessions, TODAY - dt.timedelta(days=3), "missing-number")
    start = Starter(sessions)
    assert (
        cluster_cli.main(["--cluster", "two-pointers", "--dry-run"], start, never) == 0
    )
    assert cluster_cli.main(["--cluster", "bit-cancellation", "--dry-run"], start) == 0
    assert cluster_cli.main(["--retest", "missing-number", "--dry-run"], start) == 0
    assert start.problems == []
    out = capsys.readouterr().out
    assert "next in two-pointers: two-sum-ii-input-array-is-sorted (#167)" in out
    assert "re-test due: missing-number" in out
    assert "cold re-test 1/2: missing-number" in out


def test_a_finished_cluster_says_so(
    sessions: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    start = Starter(sessions)
    assert cluster_cli.main(["--cluster", "intervals"], start, lambda _s: True) == 0
    assert start.problems == []
    assert "intervals: every problem is started or accepted" in capsys.readouterr().out


def test_unknown_or_missing_cluster_fails(
    sessions: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cluster_cli.main(["--cluster", "graphs"], Starter(sessions)) == 1
    assert cluster_cli.main(["--cluster"], Starter(sessions)) == 1
    assert cluster_cli.main(["--retest"], Starter(sessions)) == 1
    err = capsys.readouterr().err
    assert "unknown cluster 'graphs'" in err
    assert "bit-cancellation" in err
    assert "usage" in err


def test_retest_logs_an_event_after_a_postmortem(
    sessions: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    solve(sessions, TODAY - dt.timedelta(days=4), "missing-number")
    start = Starter(sessions)
    assert cluster_cli.main(["--retest", "missing-number"], start) == 0
    assert start.problems[0][0] == "missing-number"
    assert "do NOT submit" in start.problems[0][1]
    assert "node" in start.problems[0][1]
    assert start.cluster == "bit-cancellation"
    assert progress.history("missing-number", sessions).retests == 1
    assert "re-test 1/2 logged" in capsys.readouterr().out
    assert progress.due_retests(sessions) == []


def test_retest_without_a_postmortem_is_not_logged(
    sessions: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    solve(sessions, TODAY - dt.timedelta(days=4), "two-sum")
    start = Starter(sessions, postmortem=False)
    assert cluster_cli.main(["--retest", "two-sum"], start) == 0
    assert start.cluster is None
    assert progress.history("two-sum", sessions).retests == 0
    assert "re-test not logged" in capsys.readouterr().out


def test_retest_of_an_unsolved_problem_is_refused(
    sessions: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    start = Starter(sessions)
    assert cluster_cli.main(["--retest", "two-sum"], start) == 1
    assert start.problems == []
    assert "not solved yet" in capsys.readouterr().err


def test_live_check_fails_open(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> object:
        raise OSError

    monkeypatch.setattr(cluster_cli, "build_client", boom)
    assert cluster_cli.accepted_on_leetcode("missing-number") is False


def test_live_check_reports_an_accepted_problem(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[object] = []

    class Client:
        post = "post"

    def check(post: object, slugs: list[str]) -> _live_solved.LiveSolved:
        seen.extend([post, *slugs])
        return _live_solved.LiveSolved(solved=frozenset({"missing-number"}))

    monkeypatch.setattr(cluster_cli, "build_client", Client)
    monkeypatch.setattr(cluster_cli, "check_solved", check)
    assert cluster_cli.accepted_on_leetcode("missing-number") is True
    assert cluster_cli.accepted_on_leetcode("two-sum") is False
    assert seen[:2] == ["post", "missing-number"]


def test_a_silent_live_check_serves_the_problem(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def silent(_q: str, _v: dict[str, object]) -> _leetcode.GraphQLResult:
        return _leetcode.GraphQLResult(data=None, transport_error="offline")

    class Client:
        post = staticmethod(silent)

    monkeypatch.setattr(cluster_cli, "build_client", Client)
    assert cluster_cli.accepted_on_leetcode("missing-number") is False


def test_both_retests_done_means_nothing_more(
    sessions: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    solve(sessions, TODAY - dt.timedelta(days=20), "missing-number")
    log(sessions, TODAY, "missing-number", {"event": "retest"}, {"event": "retest"})
    start = Starter(sessions)
    assert cluster_cli.main(["--retest", "missing-number"], start) == 0
    assert start.problems == []
    assert "both re-tests of missing-number are done" in capsys.readouterr().out
    assert cluster_cli.main(["due", "extra"], start) == 1


def test_repl_main_dispatches_cluster_commands(
    sessions: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert leetcode_repl.main(["due"]) == 0
    assert capsys.readouterr().out == "no re-tests due\n"
    started: list[tuple[str, list[str]]] = []

    def fake_claude(model: str, problem: list[str]) -> int:
        started.append((model, problem))
        return 0

    handed: list[str] = []

    def fake_local(slug: str, *_rest: object) -> int:
        handed.append(slug)
        return 0

    monkeypatch.setattr(leetcode_repl, "run_claude", fake_claude)
    monkeypatch.setattr(local_session, "run", fake_local)
    monkeypatch.setattr(cluster_cli, "accepted_on_leetcode", never)
    assert leetcode_repl.main(["--cluster", "intervals"]) == 0
    assert started == [("sonnet", ["merge-intervals"])]
    assert leetcode_repl.main(["--local", "--cluster", "intervals"]) == 0
    assert handed == ["merge-intervals"]
