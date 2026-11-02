"""Request validation and result shapes (DOCS-coach-relay.md sections 2 and 4)."""

from __future__ import annotations

from typing import Any

import pytest

from leetcode_coach.relay import protocol

RID = "01JAXY0000000000000000000Z"
DEV = "3f2a7c1e-9b4d-4e6f-8a1b-2c3d4e5f6a7b"
SID = "20261023-170448-5b71"


def _req(kind: str, body: dict[str, Any], **extra: object) -> dict[str, Any]:
    return {"rid": RID, "kind": kind, "dev": DEV, "body": body, **extra}


@pytest.mark.parametrize(
    "rid",
    ["", "short", "01JAXY000000000000000000IL", 7, None, "01jaxy0000000000000000000z"],
)
def test_a_bad_rid_gets_no_result(rid: object) -> None:
    with pytest.raises(protocol.BadRidError):
        protocol.parse({**_req("hint", {"session": SID}), "rid": rid}, "phone")
    with pytest.raises(protocol.BadRidError):
        protocol.parse([1], "phone")


def test_a_good_request_drops_unknown_fields() -> None:
    req = protocol.parse(
        _req("chat", {"session": SID, "text": "hi", "evil": 1}, created=5, x=1),
        "desktop",
    )
    assert req == protocol.Request(
        RID, "chat", DEV, {"session": SID, "text": "hi"}, "desktop"
    )


GOOD = [
    ("session_start", {"slug": "missing-number"}),
    ("session_end", {"session": SID}),
    ("hint", {"session": SID}),
    ("reveal", {"session": SID}),
    ("chat", {"session": SID, "text": "x" * 8192}),
    ("run_code", {"session": SID, "code": "var f = 1"}),
    ("grade_step", {"session": SID, "step": 1, "answer": "n <= 10^4"}),
    ("grade_step", {"session": SID, "step": 3, "picks": ["XOR"] * 30}),
    ("grade_step", {"session": SID, "step": 4, "force": True}),
]


@pytest.mark.parametrize(("kind", "body"), GOOD)
def test_every_kind_parses(kind: str, body: dict[str, Any]) -> None:
    assert protocol.parse(_req(kind, body), "phone").body == body


BAD = [
    ("rm -rf", {}),
    ("session_start", {"slug": "Missing Number"}),
    ("session_start", {"slug": "a" * 101}),
    ("session_start", {}),
    ("chat", {"session": "../../etc", "text": "hi"}),
    ("chat", {"session": SID, "text": "é" * 4097}),
    ("chat", {"session": SID, "text": "   "}),
    ("chat", {"session": SID, "text": 5}),
    ("grade_step", {"session": SID, "step": 4, "answer": "x"}),
    ("grade_step", {"session": SID, "step": 6, "answer": "x"}),
    ("grade_step", {"session": SID, "step": True, "answer": "x"}),
    ("grade_step", {"session": SID, "step": 3, "picks": ["XOR"] * 31}),
    ("grade_step", {"session": SID, "step": 3, "picks": ["x" * 65]}),
    ("grade_step", {"session": SID, "step": 3, "picks": "XOR"}),
    ("grade_step", {"session": SID, "step": 2, "force": "yes"}),
    ("run_code", {"session": SID}),
]


@pytest.mark.parametrize(("kind", "body"), BAD)
def test_bad_bodies_are_bad_requests(kind: str, body: dict[str, Any]) -> None:
    with pytest.raises(protocol.BadRequestError):
        protocol.parse(_req(kind, body), "phone")


@pytest.mark.parametrize(
    "raw",
    [
        _req("hint", {"session": SID}, dev="not-a-uuid"),
        {**_req("hint", {}), "body": []},
        {**_req("hint", {"session": SID}), "padding": "x" * 17000},
    ],
)
def test_dev_body_and_size_are_checked(raw: dict[str, Any]) -> None:
    with pytest.raises(protocol.BadRequestError):
        protocol.parse(raw, "phone")


def test_results_carry_time_and_rev() -> None:
    assert protocol.ok({"a": 1}, at=5, state_rev=2) == {
        "ok": True,
        "at": 5,
        "state_rev": 2,
        "data": {"a": 1},
    }
    err = protocol.failure("rate_limited", "slow down", at=7, retry=True, after=3)
    assert err == {
        "ok": False,
        "at": 7,
        "code": "rate_limited",
        "error": "slow down",
        "retry": True,
        "after": 3,
    }
    assert protocol.ok_retryable("model_error")
    assert not protocol.ok_retryable("bad_request")
