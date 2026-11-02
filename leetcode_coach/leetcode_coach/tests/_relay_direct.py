"""The backend without threads or HTTP: a scripted in-process ``ask``."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from leetcode_coach.relay import protocol
from leetcode_coach.relay.coach import Coach, Deps
from leetcode_coach.relay.probe import AcceptedProbe
from leetcode_coach.tests._relay_statements import MISSING_NUMBER
from leetcode_coach.tests._relay_support import DEV, Clock, FakeProbe, rid

if TYPE_CHECKING:
    from pathlib import Path


class FakeAsk:
    """``claude_cli.ask`` in-process: scripted answers by kind, every call kept."""

    def __init__(
        self, coach: list[dict[str, Any]], haiku: list[dict[str, Any]] | None = None
    ) -> None:
        self.script = {"coach": list(coach), "haiku": list(haiku or [])}
        self.calls: list[dict[str, Any]] = []

    def __call__(self, args: list[str], prompt: str, **kw: Any) -> dict[str, Any]:
        kind = "haiku" if "haiku" in args else "coach"
        self.calls.append({"kind": kind, "args": args, "prompt": prompt, **kw})
        answer = self.script[kind].pop(0) if self.script[kind] else {"result": "?"}
        return {"session_id": "s1", **answer} if kind == "coach" else answer

    def prompts(self, kind: str = "coach") -> list[str]:
        """What reached the model of `kind`."""
        return [c["prompt"] for c in self.calls if c["kind"] == kind]


def make_coach(tmp_path: Path, ask: FakeAsk, **deps: Any) -> Coach:
    """A backend with no threads, a fake ask and dry-run cards."""
    base: dict[str, Any] = {
        "state_dir": tmp_path / "relay",
        "ask": ask,
        "fetch": lambda _slug: ("Missing Number", MISSING_NUMBER),
        "probe": AcceptedProbe(FakeProbe(), monotonic=Clock()),
        "cards_dry_run": True,
    }
    return Coach(Deps(**(base | deps)))


def req(kind: str, transport: str = "desktop", **body: object) -> protocol.Request:
    """A validated request, as the lane hands it over."""
    raw = {"rid": rid(), "kind": kind, "dev": DEV, "body": body}
    return protocol.parse(raw, transport)


def started(coach: Coach) -> str:
    """Start Missing Number (the opener must already be scripted); its sid."""
    result = coach.handle(req("session_start", slug="missing-number"))
    assert result["ok"], result
    return str(result["data"]["session"])


def grade(coach: Coach, sid: str, step: int, **body: Any) -> dict[str, Any]:
    """One ``grade_step`` result."""
    return coach.handle(req("grade_step", session=sid, step=step, **body))
