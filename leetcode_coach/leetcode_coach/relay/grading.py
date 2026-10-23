"""``grade_step``: grade steps 1, 2, 3 and 5, or let kuhy continue (force).

1 and 5 go to the model grader (`graders`), 2 to the CLI's own phase gate
(`PhaseGate.screen` logs ``req`` + ``req_check``), 3 to the mechanical
toolbox grader. Every graded try is one ``grade`` event; the step machine
reads them back (`steps`). The grade reaches the coach as a note on its next
turn and the chat as a ``system`` line at once. A step-5 pass builds the
cards and ends the session (``done``); so does forcing step 5, without cards.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from leetcode_coach import leak, phase
from leetcode_coach.relay import cards, graders, steps, toolbox_grade, turns
from leetcode_coach.relay.errors import CoachError
from leetcode_coach.relay.session import grade_line

if TYPE_CHECKING:
    from leetcode_coach.answer_key import Answer
    from leetcode_coach.relay.coach import Coach
    from leetcode_coach.relay.session import Session
    from leetcode_coach.toolbox import Toolbox

REQ_STEP: Final = 2
TOOLBOX_STEP: Final = 3
POSTMORTEM_STEP: Final = 5
READS_AS_CODE: Final = (
    "This reads as code. List the properties the operation must have, in words."
)
NAMES_A_TOOL: Final = (
    "This names an operation or a structure. List the properties it must have "
    "instead, without naming it."
)


def _requirements(session: Session, answer: str, box: Toolbox) -> tuple[str, str, str]:
    """Step 2 through the phase gate; a list that is code or names a tool fails."""
    text = answer.strip()
    words = phase.REQ_RE.sub("", text, count=1).strip()
    if phase.regex_verdict(words) is True:
        return "fail", READS_AS_CODE, "toolbox"
    if leak.leaked_names(words, [], box):
        return "fail", NAMES_A_TOOL, "toolbox"
    session.gate.screen(text if phase.REQ_RE.match(text) else f"req: {text}")
    check = [e for e in session.events() if e.get("event") == "req_check"][-1]
    via = str(check.get("via") or "unverified")
    if check.get("verdict") == "pass":
        return "pass", "", via
    if check.get("verdict") == "unverified":
        return "pass", graders.UNVERIFIED, "unverified"
    missing = [str(m) for m in check.get("missing", []) if m in box.properties]
    lines = [f"- {phase.property_line(m, box)}" for m in missing]
    return "partial", "\n".join(["It does not yet say:", *lines]), via


def _toolbox(picks: list[str], key: Answer, box: Toolbox) -> tuple[str, str, str]:
    unknown = [p for p in picks if toolbox_grade.resolve(p, box) is None]
    if unknown:
        msg = "Not in the toolbox: " + ", ".join(unknown)
        raise CoachError(msg, code="bad_request")
    grade, feedback = toolbox_grade.grade(picks, key, box)
    return grade, feedback, "toolbox"


def _graded(
    coach: Coach, session: Session, n: int, body: dict[str, Any]
) -> tuple[str, str, str]:
    key = coach.deps.answers()[session.slug]
    box = coach.deps.box()
    if n == TOOLBOX_STEP:
        return _toolbox(list(body["picks"]), key, box)
    if n == REQ_STEP:
        return _requirements(session, str(body["answer"]), box)
    text = turns.statement(coach, session) or session.slug
    got = graders.model_grade(n, text, str(body["answer"]), key, coach.deps.ask)
    users = [str(v["text"]) for v in session.chat.values() if v["role"] == "kuhy"]
    feedback = graders.safe_feedback(
        got.feedback,
        step=n,
        key=key,
        box=box,
        kuhy_texts=users,
        code_seen=session.gate.code_seen(),
    )
    return got.grade, feedback, got.via


def _record(session: Session, event: dict[str, Any]) -> int | None:
    """Log one grade event, show it, note it for the coach; the step now open."""
    session.log_event("grade", **event)
    kind, text = grade_line(event)
    session.add("system", kind, text, int(event["at"]))
    current = steps.open_step(steps.derive(session.events()))
    nxt = None if current is None else current.n
    what = "continued without a pass" if event["forced"] else f"graded {event['grade']}"
    opened = "all steps done" if nxt is None else f"step {nxt} open"
    note = f"[app: step {event['step']} {what} on try {event['attempt']}; {opened}]"
    session.notes.append(note)
    return nxt


def _force(coach: Coach, session: Session, step: steps.Step) -> dict[str, Any]:
    if not step.can_force:
        msg = f"You can continue after {steps.FORCE_AFTER} tries without a pass."
        raise CoachError(msg, code="cannot_force")
    last = step.last or {}
    event = {"step": step.n, "grade": last.get("grade") or "fail"}
    event |= {"attempt": step.attempts, "forced": True, "feedback": ""}
    event |= {"via": last.get("via") or "unverified", "at": coach.now()}
    nxt = _record(session, event)
    if step.n == POSTMORTEM_STEP:
        coach.end(session, "done")
    return {"step": step.n, "forced": True, "next_step": nxt}


def grade_step(coach: Coach, session: Session, body: dict[str, Any]) -> dict[str, Any]:
    """Grade (or force) ``body.step`` of the live session."""
    n = int(body["step"])
    step = steps.derive(session.events())[n - 1]
    if body.get("force") is True and n == steps.IMPLEMENT:
        msg = "Step 4 passes only when LeetCode shows an Accepted."
        raise CoachError(msg, code="cannot_force")
    if step.status == "locked":
        msg = f"Step {n} opens once step {n - 1} is passed or continued."
        raise CoachError(msg, code="step_locked")
    if step.done:
        msg = f"Step {n} is already done."
        raise CoachError(msg, code="step_done")
    if body.get("force") is True:
        return _force(coach, session, step)
    attempt = step.attempts + 1
    grade, feedback, via = _graded(coach, session, n, body)
    event = {"step": n, "grade": grade, "attempt": attempt, "forced": False}
    event |= {"via": via, "feedback": feedback, "at": coach.now()}
    nxt = _record(session, event)
    after = steps.derive(session.events())[n - 1]
    data: dict[str, Any] = {
        "step": n,
        "grade": grade,
        "feedback": feedback,
        "attempt": attempt,
        "can_force": after.can_force,
        "via": via,
        "next_step": nxt,
    }
    if n == POSTMORTEM_STEP and grade == "pass":
        key = coach.deps.answers()[session.slug]
        data["cards"] = cards.build(
            session, key.entries, dry_run=coach.deps.cards_dry_run
        )
        coach.end(session, "done")
    return data
