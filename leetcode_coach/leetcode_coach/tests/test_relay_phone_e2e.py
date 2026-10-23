"""TODO-coach-ui.md "Done", phone path: the scripted session through RTDB.

The phone PUTs ``requests/{rid}/req`` into an in-process fake RTDB (REST +
SSE) and polls ``requests/{rid}/result``; the relay streams the requests and
mirrors ``state``, ``chat`` and ``heartbeat``. Same flow and assertions as
the desktop (``_relay_flow``).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from leetcode_coach.relay.rtdb import Rtdb
from leetcode_coach.tests import _relay_flow as flow
from leetcode_coach.tests import _relay_support as rs
from leetcode_coach.tests._fake_rtdb import FakeRtdb
from leetcode_guard.tests._paths_fixture import _isolate_paths

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

__all__ = ["_isolate_paths"]  # the guard's paths, redirected for every test here


@pytest.fixture
def phone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[rs.Rig, FakeRtdb]]:
    root = rs.fake_claude(tmp_path, monkeypatch, **flow.SCRIPT)
    rs.seed_guard()
    with FakeRtdb.start() as fake:
        made = rs.make_rig(tmp_path, heartbeat_s=0.1, rescan_s=0.2)
        made.extra["claude"] = root
        made.relay.link_phone(Rtdb(fake.url, lambda: "tok"))
        yield made, fake
        made.relay.stop()


def phone_ends(fake: FakeRtdb) -> flow.Ends:
    def send(kind: str, **body: object) -> dict[str, Any]:
        rid = rs.rid()
        req = {
            "kind": kind,
            "dev": rs.DEV,
            "created": {".sv": "timestamp"},
            "body": body,
        }
        fake.write(f"requests/{rid}/req", req)
        raw = rs.wait_for(lambda: fake.read(f"requests/{rid}/result"), timeout=15)
        return dict(json.loads(raw))

    def state() -> dict[str, Any]:
        return dict(json.loads(rs.wait_for(lambda: fake.read("state"))))

    def chat(after: str | None) -> dict[str, Any]:
        lines = fake.read("chat") or {}
        return {k: v for k, v in lines.items() if after is None or k > after}

    return flow.Ends(send, state, chat)


def test_a_full_session_from_the_phone(phone: tuple[rs.Rig, FakeRtdb]) -> None:
    rig, fake = phone
    flow.run_flow(rig, phone_ends(fake))
    beat = rs.wait_for(lambda: fake.read("heartbeat"))
    assert isinstance(beat["beat"], int)
    assert beat["version"] == 1
    rs.wait_for(lambda: fake.read("heartbeat")["state_rev"] == rig.relay.coach.rev)
    assert json.loads(fake.read("state"))["rev"] == rig.relay.coach.rev
    assert all(
        set(v) <= {"role", "kind", "text", "at"} for v in fake.read("chat").values()
    )
