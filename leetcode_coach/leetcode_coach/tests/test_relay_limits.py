"""Rate limit, size caps and bad requests on both paths (contract 1 and 4)."""

from __future__ import annotations

import http.client
import json
from typing import TYPE_CHECKING, Any

import pytest

from leetcode_coach.relay.rtdb import Rtdb
from leetcode_coach.tests import _relay_support as rs
from leetcode_coach.tests._fake_rtdb import FakeRtdb

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[rs.Rig]:
    rs.fake_claude(tmp_path, monkeypatch, haiku=[], coach=[])
    made = rs.make_rig(tmp_path, pace_s=100.0)
    yield made
    made.relay.stop()


def _raw(
    rig: rs.Rig, method: str, path: str, body: bytes = b"", **headers: str
) -> tuple[int, Any]:
    conn = http.client.HTTPConnection("127.0.0.1", rig.relay.port, timeout=10)
    conn.putrequest(method, path, skip_host="Host" in headers)
    for name, value in headers.items():
        conn.putheader(name, value)
    if method == "POST":
        conn.putheader("Content-Length", headers.get("Length", str(len(body))))
    conn.endheaders(body)
    resp = conn.getresponse()
    status, data = resp.status, json.loads(resp.read())
    conn.close()
    return status, data


def _req(kind: str = "hint", rid: str | None = None, **body: object) -> dict[str, Any]:
    return {"rid": rid or rs.rid(), "kind": kind, "dev": rs.DEV, "body": body}


def test_http_refuses_what_the_contract_refuses(rig: rs.Rig) -> None:
    json_ = {"Content-Type": "application/json"}
    big = json.dumps(_req(text="x" * 17000)).encode()
    assert _raw(rig, "POST", "/coach/requests", big, **json_)[0] == 413
    assert (
        _raw(rig, "POST", "/coach/requests", b"{}", **{"Content-Type": "text/plain"})[0]
        == 415
    )
    assert _raw(rig, "POST", "/coach/requests", b"{", **json_)[0] == 400
    assert _raw(rig, "POST", "/coach/requests", b"{}", **json_, Length="x")[0] == 400
    assert _raw(rig, "POST", "/coach/requests", b"[]", **json_)[0] == 400
    bad_rid = json.dumps(_req(rid="nope")).encode()
    assert _raw(rig, "POST", "/coach/requests", bad_rid, **json_)[0] == 400
    assert _raw(rig, "POST", "/coach/other", b"{}", **json_)[0] == 404
    assert _raw(rig, "GET", "/coach/nope")[0] == 404
    assert _raw(rig, "GET", "/coach/requests/" + rs.rid())[0] == 404
    assert _raw(rig, "GET", "/coach/requests/not-a-rid")[0] == 404
    assert _raw(rig, "GET", "/coach/state", Host="evil.example:8777")[0] == 403
    assert _raw(rig, "POST", "/coach/requests", b"{}", Host="evil.example")[0] == 403


def test_a_bad_request_is_answered_and_remembered(rig: rs.Rig) -> None:
    raw = _req("rm -rf")
    status, got = rs.http(rig, "POST", "/coach/requests", raw)
    assert status == 200
    assert got["code"] == "bad_request"
    assert rs.http(rig, "POST", "/coach/requests", raw)[1] == got
    assert rs.http(rig, "GET", f"/coach/requests/{raw['rid']}")[1] == {"result": got}
    huge = _req("chat", session="20261023-170448-5b71", text="é" * 4097)
    assert rs.http(rig, "POST", "/coach/requests", huge)[1]["code"] == "bad_request"


def test_more_than_five_waiting_is_rate_limited(rig: rs.Rig) -> None:
    sent = [_req(session="20261023-170448-5b71") for _ in range(7)]
    answers = [rs.http(rig, "POST", "/coach/requests", r) for r in sent]
    rs.wait_for(lambda: rig.relay.lane.busy is None)
    assert [a[0] for a in answers[:6]] == [202] * 6
    status, limited = answers[6]
    assert status == 200
    assert limited["code"] == "rate_limited"
    assert limited["retry"] is True
    assert limited["retry_after_ms"] == 500_000
    first = rs.http(rig, "GET", f"/coach/requests/{sent[0]['rid']}")[1]["result"]
    assert first["code"] == "not_live"
    assert rs.http(rig, "GET", f"/coach/requests/{sent[1]['rid']}")[1] == {
        "result": None
    }
    rig.relay.lane.busy = sent[1]["rid"]
    assert rs.http(rig, "GET", "/coach/heartbeat")[1]["busy"] == sent[1]["rid"]
    rig.relay.lane.busy = None


@pytest.fixture
def phone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[rs.Rig, FakeRtdb]]:
    root = rs.fake_claude(tmp_path, monkeypatch, haiku=[], coach=[])
    with FakeRtdb.start() as fake:
        made = rs.make_rig(tmp_path, heartbeat_s=0.05, rescan_s=0.1)
        made.extra["claude"] = root
        made.relay.link_phone(Rtdb(fake.url, lambda: "tok"))
        yield made, fake
        made.relay.stop()


def _result(fake: FakeRtdb, rid: str) -> dict[str, Any]:
    return dict(json.loads(rs.wait_for(lambda: fake.read(f"requests/{rid}/result"))))


def test_the_phone_path_checks_ids_kinds_and_sizes(
    phone: tuple[rs.Rig, FakeRtdb],
) -> None:
    rig, fake = phone
    fake.write("requests/not-a-ulid/req", {"kind": "hint", "dev": rs.DEV, "body": {}})
    unknown = rs.rid()
    fake.write(f"requests/{unknown}/req", {"kind": "shell", "dev": rs.DEV, "body": {}})
    assert _result(fake, unknown)["code"] == "bad_request"
    big = rs.rid()
    fake.write(
        f"requests/{big}/req",
        {"kind": "chat", "dev": rs.DEV, "body": {"text": "x" * 17000}},
    )
    assert _result(fake, big)["code"] == "bad_request"
    ended = rs.rid()
    fake.write(
        f"requests/{ended}/req",
        {"kind": "hint", "dev": rs.DEV, "body": {"session": "20261023-170448-5b71"}},
    )
    first = _result(fake, ended)
    assert first["code"] == "not_live"
    fake.write(f"requests/{ended}/result", None)
    fake.write(
        f"requests/{ended}/req",
        {"kind": "hint", "dev": rs.DEV, "body": {"session": "20261023-170448-5b71"}},
    )
    assert _result(fake, ended) == first  # re-answered from the done-map, not re-run
    assert fake.read("requests/not-a-ulid/result") is None
    assert rs.calls(rig.extra["claude"]) == []
