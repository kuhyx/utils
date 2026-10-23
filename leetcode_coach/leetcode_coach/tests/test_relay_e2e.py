"""TODO-coach-ui.md "Done", desktop path: the scripted session over loopback.

The flow and its assertions live in ``_relay_flow``; here it runs over the
real HTTP API on port 0, with the guard's paths redirected (so the data dir
check cannot race the live harvester).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from leetcode_coach.tests import _relay_flow as flow
from leetcode_coach.tests import _relay_support as rs
from leetcode_guard.tests._paths_fixture import _isolate_paths

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

__all__ = ["_isolate_paths"]  # the guard's paths, redirected for every test here


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[rs.Rig]:
    root = rs.fake_claude(tmp_path, monkeypatch, **flow.SCRIPT)
    rs.seed_guard()
    made = rs.make_rig(tmp_path)
    made.extra["claude"] = root
    yield made
    made.relay.stop()


def desktop(rig: rs.Rig) -> flow.Ends:
    def state() -> dict[str, Any]:
        return dict(rs.http(rig, "GET", "/coach/state")[1])

    def chat(after: str | None) -> dict[str, Any]:
        query = "" if after is None else f"?after={after}"
        return dict(rs.http(rig, "GET", f"/coach/chat{query}")[1])

    return flow.Ends(lambda kind, **body: rs.call(rig, kind, **body), state, chat)


def test_a_full_session_on_the_desktop(rig: rs.Rig) -> None:
    flow.run_flow(rig, desktop(rig))
    status, beat = rs.http(rig, "GET", "/coach/heartbeat")
    assert status == 200
    assert beat["state_rev"] == rig.relay.coach.rev
    assert beat["version"] == 1
    assert "busy" not in beat
