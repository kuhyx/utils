"""`review-list` and `review-finish`: stdout is the interface, so assert on it."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from leetcode_coach import flagged, progress, review_cli, review_ledger, session_log
from leetcode_coach.tests._review_support import fake_guard, flagged_row

if TYPE_CHECKING:
    from pathlib import Path


def _events(slug: str) -> list[dict[str, Any]]:
    return session_log.read(session_log.log_path(slug))


def _rows() -> list[dict[str, Any]]:
    if not review_ledger.LEDGER_PATH.exists():
        return []
    entries: list[dict[str, Any]] = json.loads(
        review_ledger.LEDGER_PATH.read_text(encoding="utf-8")
    )["entries"]
    return entries


def _nothing_written(slug: str = "two-sum") -> bool:
    return not _events(slug) and not _rows()


def test_review_list_prints_every_flagged_solve_with_its_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_guard(tmp_path, monkeypatch, "two-sum", "3sum")
    assert review_cli.main(["review-list"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        flagged.evidence_line(flagged_row("two-sum")),
        flagged.evidence_line(flagged_row("3sum")),
    ]


def test_review_list_says_nothing_to_review_when_nothing_is_flagged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_guard(tmp_path, monkeypatch)
    assert review_cli.main(["review-list"]) == 0
    assert capsys.readouterr().out == "nothing to review\n"


def test_review_list_never_shows_a_guard_failure_as_nothing_to_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_guard(tmp_path, monkeypatch, code=1)
    assert review_cli.main(["review-list"]) == review_cli.EXIT_UNCHECKED != 0
    out = capsys.readouterr().out
    assert out.startswith("could not check: ")
    assert "nothing to review" not in out


def test_review_finish_logs_the_event_and_signs_a_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_guard(tmp_path, monkeypatch, "two-sum")
    url = "https://leetcode.com/problems/two-sum/description/"
    args = ["review-finish", url, "--cause", "missing-idea", "--module", "hashing"]
    assert review_cli.main(args) == 0
    (event,) = _events("two-sum")
    assert {k: v for k, v in event.items() if k != "ts"} == {
        "event": "review",
        "cause": "missing-idea",
        "module": "hashing",
    }
    row, tally = _rows()
    assert (row["entry_id"], row["detail"]["cause"]) == (
        "review:two-sum",
        "missing-idea",
    )
    assert tally["entry_id"] == f"progress:{row['day']}:1:1"
    assert progress.history("two-sum").solved == progress.local_today()
    assert capsys.readouterr().out.splitlines() == [
        "review logged: two-sum, cause missing-idea, module hashing",
        "ledger row: written",
        "card: build ONE property -> operation card now (DOCS-review.md step 6)",
    ]


def test_the_target_is_how_many_solves_are_flagged_when_the_review_is_finished(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_guard(tmp_path, monkeypatch, "two-sum", "3sum", "lru-cache")
    assert review_cli.main(["review-finish", "two-sum", "--cause", "debugging"]) == 0
    fake_guard(tmp_path, monkeypatch, "3sum")
    assert review_cli.main(["review-finish", "3sum", "--cause", "debugging"]) == 0
    day = _rows()[0]["day"]
    assert [r["entry_id"] for r in _rows() if r["kind"] == "progress"] == [
        f"progress:{day}:1:3",
        f"progress:{day}:2:3",
    ]


@pytest.mark.parametrize("cause", ["statement", "debugging", "interruption"])
def test_a_cause_without_a_card_is_only_recorded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    cause: str,
) -> None:
    fake_guard(tmp_path, monkeypatch, "two-sum")
    assert review_cli.main(["review-finish", "two-sum", "--cause", cause]) == 0
    (event,) = _events("two-sum")
    assert event["cause"] == cause
    assert "module" not in event
    assert capsys.readouterr().out.splitlines() == [
        f"review logged: two-sum, cause {cause}",
        "ledger row: written",
        "card: none for this cause",
    ]


def test_idea_to_code_makes_a_card_without_a_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_guard(tmp_path, monkeypatch, "two-sum")
    assert review_cli.main(["review-finish", "two-sum", "--cause", "idea-to-code"]) == 0
    assert "card: build ONE" in capsys.readouterr().out


def test_review_finish_refuses_a_slug_that_is_not_flagged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_guard(tmp_path, monkeypatch, "3sum")
    code = review_cli.main(["review-finish", "two-sum", "--cause", "debugging"])
    assert code == review_cli.EXIT_REFUSED != 0
    assert capsys.readouterr().out == (
        "refused: two-sum is not flagged, nothing to review; nothing written\n"
    )
    assert _nothing_written()


def test_review_finish_cannot_check_is_not_a_refusal_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_guard(tmp_path, monkeypatch, stdout="boom")
    code = review_cli.main(["review-finish", "two-sum", "--cause", "debugging"])
    assert code == review_cli.EXIT_UNCHECKED
    out = capsys.readouterr().out
    assert out.startswith("could not check: ")
    assert out.endswith("; nothing written\n")
    assert _nothing_written()


@pytest.mark.parametrize(
    ("extra", "why"),
    [
        (["--cause", "missing-idea"], "--module names the unit"),
        (["--cause", "debugging", "--module", "hashing"], "--module names the unit"),
        (["--cause", "missing-idea", "--module", "../x"], "not a unit id"),
    ],
)
def test_review_finish_checks_the_module_before_anything_else(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    extra: list[str],
    why: str,
) -> None:
    fake_guard(tmp_path, monkeypatch, "two-sum")
    code = review_cli.main(["review-finish", "two-sum", *extra])
    assert code == review_cli.EXIT_REFUSED
    out = capsys.readouterr().out
    assert out.startswith("refused: ")
    assert why in out
    assert _nothing_written()


def test_review_finish_refuses_what_is_not_a_slug(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = review_cli.main(["review-finish", "Two Sum!", "--cause", "debugging"])
    assert code == review_cli.EXIT_REFUSED
    assert "not a LeetCode problem URL or slug" in capsys.readouterr().out


def test_an_unknown_cause_never_reaches_the_log(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as stop:
        review_cli.main(["review-finish", "two-sum", "--cause", "bad-luck"])
    assert stop.value.code != 0
    assert "invalid choice" in capsys.readouterr().err
    assert _nothing_written()


def test_without_a_signing_key_nothing_is_written_and_it_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_guard(tmp_path, monkeypatch, "two-sum")
    review_ledger.KEY_FILE.unlink()
    code = review_cli.main(["review-finish", "two-sum", "--cause", "debugging"])
    assert code == review_cli.EXIT_NOT_WRITTEN != 0
    out = capsys.readouterr().out
    assert out.startswith("nothing written: no signed ledger row (")
    assert "no review event either" in out
    assert _nothing_written()


def test_a_slug_with_a_row_gets_its_event_but_no_second_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_guard(tmp_path, monkeypatch, "two-sum")
    review_ledger.record("two-sum", "statement", due=1)
    assert review_cli.main(["review-finish", "two-sum", "--cause", "debugging"]) == 0
    assert [e["event"] for e in _events("two-sum")] == ["review"]
    assert [r["detail"]["cause"] for r in _rows() if r["kind"] == "credit"] == [
        "statement"
    ]
    assert len(_rows()) == 2
    assert "ledger row: already there, not written twice" in capsys.readouterr().out


def test_a_lost_event_is_reported_as_exactly_that(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_guard(tmp_path, monkeypatch, "two-sum")

    def full_disk(*_args: object, **_fields: object) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(session_log, "append", full_disk)
    code = review_cli.main(["review-finish", "two-sum", "--cause", "debugging"])
    assert code == review_cli.EXIT_NOT_WRITTEN
    out = capsys.readouterr().out
    assert out.startswith("ledger row written, review event NOT logged (")
    assert "run the same command again" in out
    assert len(_rows()) == 2
