"""grade_step's branches: fails without a model, fail-open, force, cards."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from leetcode_coach import answer_key, card_rules, make_cards, session_log
from leetcode_coach.relay import cards, graders, grading, turns
from leetcode_coach.tests._relay_direct import FakeAsk, grade, make_coach, req, started

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from leetcode_coach.relay.coach import Coach


def _verdict(grade_: str, feedback: str = "") -> dict[str, str]:
    return {"result": json.dumps({"grade": grade_, "feedback": feedback})}


def _check(verdict: str, *missing: str) -> dict[str, str]:
    return {"result": json.dumps({"verdict": verdict, "missing": list(missing)})}


def _coach(tmp_path: Path, *haiku: dict[str, Any], **deps: Any) -> tuple[Coach, str]:
    coach = make_coach(tmp_path, FakeAsk([{"result": "Hi?"}] * 3, list(haiku)), **deps)
    return coach, started(coach)


def test_step_two_fails_code_and_tool_names_without_asking(tmp_path: Path) -> None:
    coach, sid = _coach(tmp_path, _verdict("pass"), _check("incomplete", "commutative"))
    grade(coach, sid, 1, answer="n is big")
    code = grade(coach, sid, 2, answer="req: x ^= y;")["data"]
    assert (code["grade"], code["feedback"]) == ("fail", grading.READS_AS_CODE)
    named = grade(coach, sid, 2, answer="use XOR")["data"]
    assert (named["grade"], named["feedback"], named["attempt"]) == (
        "fail",
        grading.NAMES_A_TOOL,
        2,
    )
    third = grade(coach, sid, 2, answer="order does not matter")["data"]
    assert third["grade"] == "partial"
    assert third["can_force"] is True
    events = session_log.read(coach.session.log)
    assert [e["event"] for e in events].count("req_check") == 1
    forced = grade(coach, sid, 2, force=True)["data"]
    assert forced == {"step": 2, "forced": True, "next_step": 3}
    assert coach.state()["step"] == 3


def test_graders_down_pass_unverified(tmp_path: Path) -> None:
    coach, sid = _coach(tmp_path, {"result": "no json"}, {"result": "nope"})
    one = grade(coach, sid, 1, answer="n is big")["data"]
    assert (one["grade"], one["via"], one["feedback"]) == (
        "pass",
        "unverified",
        graders.UNVERIFIED,
    )
    two = grade(coach, sid, 2, answer="self-inverse")["data"]
    assert (two["grade"], two["via"]) == ("pass", "unverified")


def test_feedback_that_names_a_tool_or_quotes_the_key_is_replaced(
    tmp_path: Path,
) -> None:
    rule = answer_key.load_answers()["missing-number"].design_rule
    coach, sid = _coach(
        tmp_path,
        _verdict("fail", "Think about XOR."),
        _verdict("partial", "Hint: " + rule),
    )
    first = grade(coach, sid, 1, answer="n")["data"]
    assert first["feedback"] == graders.CONSTRAINT_HINT
    second = grade(coach, sid, 1, answer="n")["data"]
    assert second["feedback"] == graders.CONSTRAINT_HINT
    assert rule not in json.dumps(coach.chat_after(None))


def test_locks_done_and_force_rules(tmp_path: Path) -> None:
    coach, sid = _coach(tmp_path, _verdict("partial", "More."), _verdict("pass"))
    assert grade(coach, sid, 3, picks=["XOR"])["code"] == "step_locked"
    grade(coach, sid, 1, answer="n")
    assert grade(coach, sid, 1, force=True)["code"] == "cannot_force"
    grade(coach, sid, 1, answer="n")
    assert grade(coach, sid, 1, answer="n")["code"] == "step_done"
    assert grade(coach, sid, 1, force=True)["code"] == "step_done"


def _to_step(coach: Coach, sid: str, n: int) -> None:
    """Force (or pass) every step before `n`, with no model."""
    for step in range(1, n):
        if step == 3:
            grade(coach, sid, 3, picks=["XOR"])
        elif step == 4:
            session = coach.session
            session.log_event(
                "grade", step=4, grade="pass", forced=False, via="accepted"
            )
        else:
            for _ in range(3):
                grade(coach, sid, step, answer="req: x ^= y;" if step == 2 else "n")
            grade(coach, sid, step, force=True)


def test_unknown_picks_are_bad_requests(tmp_path: Path) -> None:
    coach, sid = _coach(tmp_path)
    _to_step(coach, sid, 3)
    assert grade(coach, sid, 3, picks=["telepathy"])["code"] == "bad_request"


def test_forcing_the_post_mortem_ends_without_cards(tmp_path: Path) -> None:
    coach, sid = _coach(tmp_path, *[_verdict("fail", "No.")] * 6)
    _to_step(coach, sid, 5)
    for _ in range(3):
        grade(coach, sid, 5, answer="dunno")
    forced = grade(coach, sid, 5, force=True)["data"]
    assert forced == {"step": 5, "forced": True, "next_step": None}
    assert coach.state()["session"]["end_reason"] == "done"


def test_a_real_delivery_logs_the_post_mortem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(make_cards, "OUT_DIR", tmp_path / "learn")
    monkeypatch.setattr(make_cards.anki_connect, "available", lambda: False)
    coach, sid = _coach(tmp_path, _verdict("pass"), cards_dry_run=False)
    _to_step(coach, sid, 5)
    done_ = grade(coach, sid, 5, answer="the pairs cancel")
    assert done_["ok"], done_
    done = done_["data"]
    assert done["cards"] == {"built": 1, "deck": "LeetCode", "error": None}
    assert (tmp_path / "learn" / "cards.tsv").is_file()
    assert session_log.read(coach.session.log)[-2]["event"] == "postmortem"


def test_card_failures_only_fill_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    coach, _sid = _coach(tmp_path)
    session = coach.session
    assert cards.build(session, ("nope",))["error"].startswith("no cards")
    monkeypatch.setattr(card_rules, "validate", lambda *_a: ["too long"])
    assert cards.build(session, ("XOR",))["error"] == "cards rejected: too long"
    monkeypatch.setattr(card_rules, "validate", lambda *_a: [])

    def boom(*_a: object, **_k: object) -> str:
        msg = "anki on fire"
        raise RuntimeError(msg)

    monkeypatch.setattr(make_cards, "deliver", boom)
    assert cards.build(session, ("XOR",))["error"] == "delivery failed: anki on fire"


def test_run_code_shows_its_error(tmp_path: Path) -> None:
    ran = {"examples": [], "error": "timeout"}
    coach, sid = _coach(tmp_path, run_code=lambda _c, _s: ran, fetch=lambda _s: None)
    _to_step(coach, sid, 3)
    assert coach.handle(req("run_code", session=sid, code="while(1){}"))["data"] == ran
    last = list(coach.chat_after(None).values())[-1]
    assert last == {
        "role": "system",
        "kind": "run",
        "text": turns.RUN_ERRORS["timeout"],
        "at": last["at"],
    }


def test_the_statement_fetch_fails_soft(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(_slug: str) -> object:
        msg = "offline"
        raise OSError(msg)

    monkeypatch.setattr(turns.fetch_problem, "fetch", refuse)
    assert turns.fetch_statement("x") is None
    monkeypatch.setattr(turns.fetch_problem, "fetch", lambda _s: {"isPaidOnly": True})
    assert turns.fetch_statement("x") is None
    question = {
        "questionFrontendId": "1",
        "title": "T",
        "difficulty": "Easy",
        "content": "<p>Do it.</p>",
        "codeSnippets": [],
        "topicTags": [],
        "hints": [],
    }
    monkeypatch.setattr(turns.fetch_problem, "fetch", lambda _s: question)
    got = turns.fetch_statement("x")
    assert got is not None
    assert got[0] == "T"


def test_the_post_mortem_grader_sees_the_key_properties() -> None:
    key = answer_key.load_answers()["missing-number"]
    seen: list[str] = []

    def ask(_args: list[str], prompt: str, **_kw: object) -> dict[str, str]:
        seen.append(prompt)
        return {"result": json.dumps({"grade": "pass", "feedback": 5})}

    assert graders.model_grade(5, "S", "A", key, ask).via == "unverified"
    assert "invertible" in seen[0]
    assert graders.fallback(5, key).startswith("Say which properties")
