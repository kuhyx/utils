"""The spec's scripted session, run the same way over either transport.

TODO-coach-ui.md "Done": start Missing Number, each graded step answers
pass/partial/fail with feedback, the next step is blocked until a pass or
the 3rd try, the chat round-trips, Hint logs a rung, run-code runs on real
node, a simulated Accepted passes step 4 within one poll, the post-mortem is
graded and its cards built (dry-run), and the Coach-tab history shows the
four grades and the highest rung. `Ends` is how one transport sends a
request and reads ``state`` / ``chat``.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import TYPE_CHECKING, Any

from leetcode_coach import answer_key, session_log
from leetcode_coach.tests import _relay_support as rs
from leetcode_guard import _coach_log

if TYPE_CHECKING:
    from collections.abc import Callable

OPENER = "Let's start. What limit binds here?\n<!-- rung:H0 -->"
HINT = "What happens to a value combined with itself?\n<!-- rung:H1 -->"
CODE = (
    "var missingNumber = function(nums) {\n  let x = nums.length;\n"
    "  for (let i = 0; i < nums.length; i++) x ^= i ^ nums[i];\n  return x;\n};"
)


def _haiku(**obj: object) -> dict[str, str]:
    return {"result": json.dumps(obj)}


SCRIPT: dict[str, list[dict[str, Any]]] = {
    "haiku": [
        _haiku(grade="fail", feedback="Say what the space limit rules out."),
        _haiku(grade="partial", feedback="Now say what that forces."),
        _haiku(grade="fail", feedback="Name the limit first."),
        _haiku(verdict="incomplete", missing=["self-inverse"]),
        _haiku(verdict="pass", missing=[]),
        _haiku(grade="pass", feedback=""),
    ],
    "coach": [
        {"result": OPENER},
        {"result": "Which limit did you pick, and why?"},
        {"result": HINT},
    ],
}


@dataclass
class Ends:
    """One transport: send a request, read the state, read chat lines."""

    send: Callable[..., dict[str, Any]]
    state: Callable[[], dict[str, Any]]
    chat: Callable[[str | None], dict[str, Any]]

    def step(self, n: int) -> dict[str, Any]:
        """Step `n`'s row in the current state."""
        return dict(self.state()["steps"][n - 1])


def _through_step_two(rig: rs.Rig, ends: Ends, sid: str) -> None:
    send = ends.send
    assert send("session_start", slug="two-sum")["code"] == "session_live"
    assert send("grade_step", session=sid, step=2, answer="x")["code"] == "step_locked"
    tries = [
        send("grade_step", session=sid, step=1, answer="n <= 10^4") for _ in range(3)
    ]
    assert [t["data"]["grade"] for t in tries] == ["fail", "partial", "fail"]
    assert [t["data"]["attempt"] for t in tries] == [1, 2, 3]
    assert [t["data"]["can_force"] for t in tries] == [False, False, True]
    assert tries[0]["data"]["feedback"] == "Say what the space limit rules out."
    forced = send("grade_step", session=sid, step=1, force=True)
    assert forced["data"] == {"step": 1, "forced": True, "next_step": 2}

    reply = send("chat", session=sid, text="Is it the memory limit?")
    prompts = [
        c["prompt"] for c in rs.calls(rig.extra["claude"]) if c["kind"] == "coach"
    ]
    assert prompts[1].startswith("[app: step 1 graded fail on try 1; step 1 open]")
    assert "[app: step 1 continued without a pass on try 3; step 2 open]" in prompts[1]
    assert prompts[1].endswith("Is it the memory limit?")
    lines = ends.chat("m0001")
    assert lines[reply["data"]["msg"]]["text"] == "Which limit did you pick, and why?"
    assert any(v["kind"] == "grade" and v["role"] == "system" for v in lines.values())

    early = send("chat", session=sid, text="const seen = new Set();")
    assert early["code"] == "phase_locked"
    assert "requirement list" in early["note"]
    assert send("run_code", session=sid, code=CODE)["code"] == "phase_locked"
    partial = send("grade_step", session=sid, step=2, answer="constant space, one pass")
    assert partial["data"]["grade"] == "partial"
    assert "self-inverse" in partial["data"]["feedback"]
    passed = send("grade_step", session=sid, step=2, answer="self-inverse, commutative")
    assert passed["data"] == {
        "step": 2,
        "grade": "pass",
        "feedback": "",
        "attempt": 2,
        "can_force": False,
        "via": "haiku",
        "next_step": 3,
    }


def _toolbox_to_accepted(rig: rs.Rig, ends: Ends, sid: str) -> None:
    send = ends.send
    state = ends.state()
    assert state["step"] == 3
    assert {e["name"] for e in state["toolbox"]} == {"XOR", "hash map", "sum formula"}
    assert "XOR" not in json.dumps(state["steps"])
    wrong = send("grade_step", session=sid, step=3, picks=["hash map"])
    assert wrong["data"]["grade"] == "fail"
    assert "XOR" not in wrong["data"]["feedback"]
    assert "self-inverse" in wrong["data"]["feedback"]
    assert (
        send("grade_step", session=sid, step=3, picks=["XOR"])["data"]["next_step"] == 4
    )

    hint = send("hint", session=sid)
    assert hint["data"]["rung"] == "H1"
    assert ends.state()["rung"] == "H1"
    ran = send("run_code", session=sid, code=CODE)
    assert ran["data"]["error"] is None
    assert [e["ok"] for e in ran["data"]["examples"]] == [True, True, True]

    rs.wait_for(lambda: ends.step(4)["probe"] == "not_yet")
    assert send("grade_step", session=sid, step=5, answer="x")["code"] == "step_locked"
    assert send("grade_step", session=sid, step=4, force=True)["code"] == "cannot_force"
    session = rig.relay.coach.session
    assert session is not None
    rig.probe.status = "accepted"
    rig.probe.timestamp_s = session.started // 1000 + 5
    rig.clock.now += 60
    rs.wait_for(lambda: ends.step(4)["status"] == "passed", timeout=2)
    assert ends.step(4)["probe"] == "accepted"
    assert ends.step(5)["status"] == "open"


def run_flow(rig: rs.Rig, ends: Ends) -> None:
    """The whole session; every assertion of the spec's scripted E2E."""
    before = rs.guard_digest()
    start = ends.send("session_start", slug="missing-number")
    assert start["ok"], start
    sid = start["data"]["session"]
    assert start["data"]["msg"] == "m0001"
    first = rs.calls(rig.extra["claude"])[0]
    assert first["prompt"] == "/leetcode missing-number"
    log = session_log.sessions_dir() / first["log"].rsplit("/", 1)[1]
    assert first["log"] == str(log)
    _through_step_two(rig, ends, sid)
    _toolbox_to_accepted(rig, ends, sid)
    post = ends.send("grade_step", session=sid, step=5, answer="pairs cancel out")
    assert post["data"]["grade"] == "pass"
    assert post["data"]["cards"] == {"built": 1, "deck": "LeetCode", "error": None}
    assert post["data"]["next_step"] is None
    assert ends.state()["session"]["end_reason"] == "done"
    assert ends.send("chat", session=sid, text="thanks")["code"] == "not_live"

    events = session_log.read(log)
    assert [e["event"] for e in events].count("grade") == 10
    assert all(e.get("sid") == sid for e in events if e["event"] in {"grade", "chat"})
    problem = _coach_log.read_session(log)
    assert problem is not None
    assert problem.max_rung == "H1"
    assert problem.accepted is True
    assert problem.grades is not None
    assert {k: v["grade"] for k, v in problem.grades.items()} == {
        "constraint": "fail",
        "requirements": "pass",
        "toolbox": "pass",
        "postmortem": "pass",
    }
    assert problem.grades["constraint"]["forced"] is True
    coach_calls = [c for c in rs.calls(rig.extra["claude"]) if c["kind"] == "coach"]
    assert all(c["log"] == str(log) for c in coach_calls)
    key = answer_key.load_answers()["missing-number"]
    assert key.design_rule not in log.read_text(encoding="utf-8")
    assert key.design_rule not in json.dumps(ends.chat(None))
    assert rs.guard_digest() == before
