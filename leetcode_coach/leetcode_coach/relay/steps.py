"""The five-step state machine, derived from the session log (contract 2-3).

Nothing about a step is held in memory: its status, tries and last grade are
read back from this session's events every time, so a relay restart, the CLI
writing into the same file, and the app all agree. Each step goes
``locked -> open -> passed | forced``; passing or forcing step n opens n+1.
A ``partial`` / ``fail`` keeps the step open and counts a try; after
`FORCE_AFTER` tries without a pass kuhy may continue (``can_force``).

Step 2's tries follow the CLI's count (`phase.step2_attempts`). Step 4 is
never graded: its only ``grade`` is a detected LeetCode Accepted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from leetcode_coach import phase

NAMES: Final = {
    1: "constraint",
    2: "requirements",
    3: "toolbox",
    4: "implement",
    5: "postmortem",
}
FORCE_AFTER: Final = 3
IMPLEMENT: Final = 4
REQUIREMENTS: Final = 2


@dataclass(frozen=True)
class Step:
    """One step as the state shows it."""

    n: int
    status: str
    attempts: int
    last: dict[str, Any] | None

    @property
    def done(self) -> bool:
        """Passed or forced: the next step is open."""
        return self.status in {"passed", "forced"}

    @property
    def can_force(self) -> bool:
        """Open, graded, and at least `FORCE_AFTER` tries without a pass."""
        return (
            self.status == "open"
            and self.n != IMPLEMENT
            and self.attempts >= FORCE_AFTER
        )


def _grades(events: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    return [e for e in events if e.get("event") == "grade" and e.get("step") == n]


def _last(grades: list[dict[str, Any]]) -> dict[str, Any] | None:
    tried = [g for g in grades if g.get("forced") is not True]
    if not tried:
        return None
    g = tried[-1]
    return {
        "grade": g.get("grade"),
        "feedback": g.get("feedback", ""),
        "via": g.get("via"),
        "at": g.get("at"),
    }


def _status(grades: list[dict[str, Any]], *, reachable: bool) -> str:
    if any(g.get("forced") is True for g in grades):
        return "forced"
    if any(g.get("grade") == "pass" for g in grades):
        return "passed"
    return "open" if reachable else "locked"


def derive(events: list[dict[str, Any]]) -> list[Step]:
    """Every step of the session whose events these are."""
    steps: list[Step] = []
    reachable = True
    for n in NAMES:
        grades = _grades(events, n)
        status = _status(grades, reachable=reachable)
        if n == REQUIREMENTS:  # the CLI's count, so both clients agree
            attempts = phase.step2_attempts(events)
        else:
            attempts = sum(
                1
                for g in grades
                if g.get("grade") != "pass" and g.get("forced") is not True
            )
        step = Step(n, status, attempts, _last(grades))
        steps.append(step)
        reachable = step.done
    return steps


def open_step(steps: list[Step]) -> Step | None:
    """The step kuhy is on, or None when every step is done."""
    return next((s for s in steps if s.status == "open"), None)


def rung(events: list[dict[str, Any]]) -> str | None:
    """The coach's current hint rung (its last marker)."""
    rungs = [e.get("rung") for e in events if e.get("event") == "rung"]
    return str(rungs[-1]) if rungs else None


def revealed(events: list[dict[str, Any]]) -> bool:
    """Whether kuhy typed ``reveal`` in this session."""
    return any(e.get("event") == "reveal" for e in events)


def view(step: Step, probe: str | None, probed_at: int | None) -> dict[str, Any]:
    """The step's row in the published state (section 3)."""
    row: dict[str, Any] = {"n": step.n, "name": NAMES[step.n], "status": step.status}
    if step.n == IMPLEMENT:
        return {**row, "probe": probe, "probed_at": probed_at}
    return {
        **row,
        "attempts": step.attempts,
        "can_force": step.can_force,
        "last": step.last,
    }
