"""The session backend: lifecycle, chat, hand-over, restart (contract 2-3)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
import urllib.error

from leetcode_coach import local_backend, session_log
from leetcode_coach.relay import session as session_mod
from leetcode_coach.tests._relay_direct import FakeAsk, make_coach, req, started

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

LIMIT = "You've hit your session limit · resets 3pm (Europe/Warsaw)"


def test_no_session_yet_is_a_known_empty_state(tmp_path: Path) -> None:
    coach = make_coach(tmp_path, FakeAsk([]))
    state = coach.state()
    assert state == {
        "schema": 1,
        "rev": 1,
        "step": None,
        "rung": None,
        "revealed": False,
        "chat_count": 0,
        "session": None,
        "steps": [],
    }
    assert coach.chat_after(None) == {}
    assert (
        coach.handle(req("hint", session="20261023-170448-5b71"))["code"] == "not_live"
    )


def test_end_then_a_fresh_session_clears_the_chat(tmp_path: Path) -> None:
    ask = FakeAsk([{"result": "One?"}, {"result": "Two?"}])
    coach = make_coach(tmp_path, ask)
    sid = started(coach)
    assert coach.handle(req("session_end", session=sid))["data"] == {}
    state = coach.state()
    assert state["session"]["end_reason"] == "ended"
    assert state["step"] is None
    assert coach.handle(req("chat", session=sid, text="hi"))["code"] == "not_live"
    other = started(coach)
    assert other != sid
    assert list(coach.chat_after(None)) == ["m0001"]
    assert coach.chat_after(None)["m0001"]["text"] == "Two?"
    events = session_log.read(coach.session.log)
    assert [e["event"] for e in events].count("session_start") == 2


def test_only_answer_key_problems_and_a_failed_opener_logs_nothing(
    tmp_path: Path,
) -> None:
    ask = FakeAsk([{"result": "x", "session_id": ""}])
    coach = make_coach(tmp_path, ask, fetch=lambda _slug: None)
    assert coach.handle(req("session_start", slug="two-sum"))["code"] == "no_answer_key"
    failed = coach.handle(req("session_start", slug="missing-number"))
    assert failed["code"] == "model_error"
    assert failed["retry"] is True
    assert coach.session is None
    assert not list(session_log.sessions_dir().glob("*.jsonl"))


def test_a_usage_limit_hands_over_to_the_local_model(tmp_path: Path) -> None:
    seen: list[Any] = []

    def local(
        messages: list[dict[str, str]], *, timeout: float
    ) -> local_backend.LocalReply:
        seen.append((messages[-1]["content"], timeout))
        return local_backend.LocalReply("What does a pair do?", 1.0, 5)

    ask = FakeAsk([{"result": "Start?"}, {"result": LIMIT}])
    coach = make_coach(tmp_path, ask, local_chat=local)
    sid = started(coach)
    reply = coach.handle(req("chat", session=sid, text="I am stuck"))
    assert reply["ok"]
    assert coach.session.local
    again = coach.handle(req("chat", session=sid, text="still stuck"))
    assert again["ok"]
    assert len(ask.prompts()) == 2  # the second turn never asked claude
    assert seen[-1][1] == 240.0
    assert coach.chat_after("m0003")["m0005"]["text"] == "What does a pair do?"


def test_quota_and_local_both_down_is_claude_unavailable(tmp_path: Path) -> None:
    def down(_messages: object, **_kw: object) -> local_backend.LocalReply:
        msg = "refused"
        raise urllib.error.URLError(msg)

    coach = make_coach(tmp_path, FakeAsk([{"result": LIMIT}]), local_chat=down)
    failed = coach.handle(req("session_start", slug="missing-number"))
    assert failed["code"] == "claude_unavailable"
    assert failed["resets_at"] == "3pm (Europe/Warsaw)"
    assert failed["reason"] == LIMIT


def test_reveal_goes_out_bare_and_ends_the_session(tmp_path: Path) -> None:
    ask = FakeAsk([{"result": "Hi?"}, {"result": "Here is the idea."}])
    coach = (
        make_coach(tmp_path, ask, haiku=None) if False else make_coach(tmp_path, ask)
    )
    sid = started(coach)
    coach.session.notes.append("[app: pending]")
    got = coach.handle(req("reveal", session=sid))
    assert got["data"] == {"msg": "m0003"}
    assert ask.prompts()[-1] == "reveal"
    assert coach.state()["revealed"] is True
    assert coach.state()["session"]["end_reason"] == "reveal"


def test_chat_req_lists_and_ambiguous_text(tmp_path: Path) -> None:
    haiku = [
        {"result": json.dumps({"verdict": "pass", "missing": []})},
        {"result": json.dumps({"code": False})},
    ]
    ask = FakeAsk([{"result": "Hi?"}, {"result": "Ok?"}, {"result": "Sure?"}], haiku)
    coach = make_coach(tmp_path, ask)
    sid = started(coach)
    assert coach.handle(req("chat", session=sid, text="req: self-inverse"))["ok"]
    assert any(v["kind"] == "grade" for v in coach.chat_after(None).values())
    assert coach.handle(req("chat", session=sid, text="so a = b then"))["ok"]
    assert ask.prompts("haiku")[1] == "so a = b then"


def test_a_screen_refusal_is_phase_locked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    coach = make_coach(tmp_path, FakeAsk([{"result": "Hi?"}]))
    sid = started(coach)
    monkeypatch.setattr(coach.session.gate, "screen", lambda *_a, **_k: (None, "held"))
    got = coach.handle(req("chat", session=sid, text="just words"))
    assert got["code"] == "phase_locked"
    assert got["note"] == "held"


def test_a_restart_rebuilds_the_session_from_the_log(tmp_path: Path) -> None:
    ask = FakeAsk([{"result": "Hi? <!-- rung:H0 -->"}])
    coach = make_coach(tmp_path, ask)
    sid = started(coach)
    haiku = [{"result": json.dumps({"grade": "partial", "feedback": "More."})}]
    coach.deps.ask = FakeAsk([], haiku)
    coach.session.gate.ask = coach.deps.ask
    assert coach.handle(req("grade_step", session=sid, step=1, answer="n"))["ok"]
    rev = coach.rev
    again = make_coach(tmp_path, FakeAsk([]))
    assert again.session is not None
    assert again.session.sid == sid
    assert again.session.claude_id == "s1"
    assert again.rev > rev
    kinds = [(v["role"], v["kind"]) for v in again.chat_after(None).values()]
    assert kinds == [("coach", "chat"), ("system", "grade")]
    assert again.state()["steps"][0]["attempts"] == 1
    assert again.state()["rung"] == "H0"


def test_a_broken_or_stale_pointer_restores_nothing(tmp_path: Path) -> None:
    live = tmp_path / "relay" / "live.json"
    live.parent.mkdir(parents=True)
    live.write_text("{", encoding="utf-8")
    assert make_coach(tmp_path, FakeAsk([])).session is None
    coach = make_coach(tmp_path, FakeAsk([{"result": "Hi?"}]))
    started(coach)
    record = json.loads(live.read_text(encoding="utf-8"))
    session_log.append(coach.session.log, "session_start", sid="20991231-000000-ffff")
    assert make_coach(tmp_path, FakeAsk([])).session is None
    record["log"] = str(tmp_path / "gone.jsonl")
    live.write_text(json.dumps(record), encoding="utf-8")
    assert make_coach(tmp_path, FakeAsk([])).session is None


def test_event_times_fall_back_to_ts(caplog: pytest.LogCaptureFixture) -> None:
    assert session_mod._ms({"at": 5}) == 5
    assert session_mod._ms({"ts": "2026-10-23T17:04:48+02:00"}) == 1792767888000
    assert session_mod._ms({"ts": "yesterday"}) == 0
    assert "usable time" in caplog.text
    forced = {"step": 2, "forced": True, "attempt": 3}
    assert session_mod.grade_line(forced) == (
        "grade",
        "Step 2 (requirements): continued after 3 tries.",
    )
