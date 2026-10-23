"""Toolbox grading on the real key, the Accepted probe, and smaller seams."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from leetcode_coach import answer_key, leak, toolbox
from leetcode_coach.relay import chat, config, probe, toolbox_grade, turns
from leetcode_coach.tests._relay_direct import FakeAsk, make_coach, req, started
from leetcode_coach.tests._relay_support import Clock, FakeProbe

if TYPE_CHECKING:
    from pathlib import Path

REAL = toolbox.load_safe(toolbox.TOOLBOX_PATH)
KEYS = answer_key.load_answers()


@pytest.mark.parametrize("slug", sorted(KEYS))
def test_every_key_passes_its_own_entries_and_names_none(slug: str) -> None:
    key = KEYS[slug]
    assert toolbox_grade.grade(list(key.entries), key, REAL) == ("pass", "")
    for alt in key.also_accepted:
        assert toolbox_grade.grade([alt], key, REAL)[0] in {"pass", "partial"}
    right = {*key.entries, *key.also_accepted}
    wrong = [e.name for e in REAL.entries if e.name not in right]
    verdict, feedback = toolbox_grade.grade(wrong[:1], key, REAL)
    assert verdict in {"fail", "partial"}
    assert leak.leaked_names(feedback, [], REAL) == []


def test_combined_entries_count_from_their_parts() -> None:
    combined = toolbox_grade.resolve("prefix sum + hash map", REAL)
    assert combined is not None
    parts = toolbox_grade.parts(combined, REAL)
    assert parts is not None
    assert [p.name for p in parts] == ["prefix sums", "hash map"]
    key = KEYS["subarray-sum-equals-k"]
    assert toolbox_grade.grade(["prefix sums", "hash map"], key, REAL) == ("pass", "")
    merge = toolbox_grade.resolve("sort by start + merge", REAL)
    assert merge is not None
    assert toolbox_grade.parts(merge, REAL) is None
    xor = toolbox_grade.resolve("xor", REAL)
    assert xor is not None
    assert toolbox_grade.parts(xor, REAL) is None


def test_alternatives_extras_and_misses() -> None:
    key = KEYS["missing-number"]
    assert toolbox_grade.grade(["sum / difference"], key, REAL) == ("pass", "")
    assert toolbox_grade.grade(["XOR", "heap"], key, REAL) == ("pass", "")
    verdict, feedback = toolbox_grade.grade(["XOR", "heap", "gcd"], key, REAL)
    assert verdict == "partial"
    assert feedback == toolbox_grade.TOO_MANY
    verdict, feedback = toolbox_grade.grade(["heap"], key, REAL)
    assert verdict == "fail"
    assert "self-inverse" in feedback
    spread = toolbox_grade.grade(["XOR"], KEYS["single-number-iii"], REAL)
    assert spread[0] == "partial"
    box = toolbox.Toolbox(
        (toolbox.Entry("A", (), ("p",)), toolbox.Entry("B", (), ("p",))), {"p": "m"}
    )
    ghost = answer_key.Answer("r", ("B", "Ghost"), (), ("p",), ("x",))
    assert toolbox_grade.grade(["A"], ghost, box) == ("fail", toolbox_grade.SPREAD)


def test_the_probe_is_three_valued_and_spaced(caplog: pytest.LogCaptureFixture) -> None:
    fake, clock = FakeProbe(), Clock()
    accepted = probe.AcceptedProbe(fake, monotonic=clock)
    assert accepted.due()
    assert accepted.check("missing-number", 1000) == probe.NOT_YET
    assert not accepted.due()
    clock.now += 60
    assert accepted.due()
    fake.status, fake.timestamp_s = "accepted", 0
    assert accepted.check("missing-number", 1000) == probe.NOT_YET  # older than start
    fake.timestamp_s = 2
    assert accepted.check("missing-number", 1000) == probe.ACCEPTED
    assert accepted.check("two-sum", 1000) == probe.NOT_YET
    fake.status = "unusable"
    assert accepted.check("missing-number", 1000) == probe.UNKNOWN

    def boom() -> object:
        msg = "dns"
        raise OSError(msg)

    assert probe.AcceptedProbe(boom).check("x", 0) == probe.UNKNOWN
    assert "probe failed" in caplog.text


def test_the_live_probe_uses_the_harvesters_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Client:
        post = staticmethod(lambda *_a: None)
        username = "kuhy"

    seen: list[str] = []
    monkeypatch.setattr(probe, "build_client", Client)
    monkeypatch.setattr(probe, "fetch_recent_ac", lambda _post, user: seen.append(user))
    probe.live_probe()
    assert seen == ["kuhy"]


def test_ticks_that_must_do_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    coach = make_coach(tmp_path, FakeAsk([{"result": "Hi?"}]))
    coach.tick()  # no session
    sid = started(coach)
    coach.tick()  # step 1 open, not 4
    session = coach.session
    assert session is not None
    for step in (1, 2, 3):
        session.log_event("grade", step=step, grade="pass", forced=False, via="haiku")

    def vanish(*_a: object) -> str:
        coach.session = None
        return "not_yet"

    monkeypatch.setattr(coach.deps.probe, "check", vanish)
    coach.tick()  # the session went away mid-probe
    assert session.probe is None
    coach.session = session
    monkeypatch.setattr(coach.deps.probe, "due", lambda: False)
    coach.tick()
    coach.handle(req("session_end", session=sid))
    coach.tick()
    assert session.probe is None


def test_a_restored_ended_session_and_a_refetched_statement(tmp_path: Path) -> None:
    fetched: list[str] = []

    def fetch(slug: str) -> tuple[str, str]:
        fetched.append(slug)
        return "Missing Number", "statement"

    coach = make_coach(tmp_path, FakeAsk([{"result": "Hi?"}]), fetch=fetch)
    sid = started(coach)
    coach.session.log_event("rung", rung="H1")
    coach.handle(req("session_end", session=sid))
    again = make_coach(tmp_path, FakeAsk([]), fetch=fetch)
    assert again.session is not None
    assert again.session.end_reason == "ended"
    assert again.session.statement is None
    assert turns.statement(again, again.session) == "statement"
    assert again.session.gate.known == "statement"
    assert fetched == ["missing-number", "missing-number"]


def test_env_and_config_seams(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    coach = make_coach(tmp_path, FakeAsk([{"result": "Hi?"}]))
    started(coach)
    session = coach.session
    session.cluster = None
    assert chat._env(session) == {"LEETCODE_COACH_LOG": str(session.log)}
    monkeypatch.setenv(config.DIR_ENV, str(tmp_path / "d"))
    monkeypatch.setenv(config.PORT_ENV, "9999")
    monkeypatch.setenv(config.RTDB_ENV, "http://127.0.0.1:1")
    monkeypatch.setenv(config.CARDS_DRY_RUN_ENV, "1")
    assert config.state_dir() == tmp_path / "d"
    assert config.port() == 9999
    assert config.rtdb_url() == "http://127.0.0.1:1"
    assert config.cards_dry_run()
    monkeypatch.delenv(config.DIR_ENV)
    monkeypatch.delenv(config.PORT_ENV)
    assert config.state_dir() == config.DEFAULT_DIR
    assert config.port() == config.DEFAULT_PORT
