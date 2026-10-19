# Copyright (c) 2026 Krzysztof Rudnicki
"""Tests for ``Claim.grab_held``: whether a locker's X grab is ACTUALLY held.

A claim is published before the window grabs, and leetcode-guard's study mode
releases the grab while its claim lives on -- so "a claim exists" is not "the
input is locked". ``grab_held`` is the second answer, rewritten in place in
the flock-held claim file, and :func:`gatelock.held_grabs` is how a reader
(root included) asks for it.
"""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from gatelock import Arbiter, Claim, held_grabs
from gatelock._arbiter import RANK_SCREEN_LOCKER

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_BASE = {
    "app": "leetcode_guard",
    "rank": 150,
    "pid": 1,
    "started": "2026-10-19T08:00:00+00:00",
    "disable_vt": True,
    "instance_id": "abc",
}


def _arbiter(runtime: Path, grab: str = "global") -> Arbiter:
    """A published arbiter under `runtime`."""
    arbiter = Arbiter(
        "leetcode_guard",
        RANK_SCREEN_LOCKER,
        grab=grab,
        disable_vt=True,
        runtime_dir=runtime,
    )
    arbiter.publish()
    return arbiter


@pytest.fixture
def arb(tmp_path: Path) -> Iterator[Arbiter]:
    """A published global-grab arbiter, released afterwards."""
    arbiter = _arbiter(tmp_path / "rt")
    yield arbiter
    arbiter.release()


def _claim_file(arbiter: Arbiter) -> Path:
    (path,) = arbiter._claims_dir.glob("*.json")
    return path


class TestSerialisation:
    """``grab_held`` is always written, and inferred for old writers."""

    def test_defaults_false_and_is_always_serialised(self) -> None:
        """A fresh claim has not grabbed anything yet."""
        claim = Claim(**_BASE, grab="global")
        assert claim.grab_held is False
        assert json.loads(claim.to_json())["grab_held"] is False

    @pytest.mark.parametrize(
        "case", [("global", True), ("local", True), ("none", False)]
    )
    def test_old_writer_without_the_key_infers_from_grab(
        self, case: tuple[str, bool]
    ) -> None:
        """JSON from a pre-0.11 writer reads as held whenever it declared a grab."""
        grab, held = case
        claim = Claim.from_json(json.dumps({**_BASE, "grab": grab}))
        assert claim is not None
        assert claim.grab_held is held

    def test_explicit_key_wins_over_inference(self) -> None:
        """A new writer saying False is believed even with a global grab."""
        text = json.dumps({**_BASE, "grab": "global", "grab_held": False})
        claim = Claim.from_json(text)
        assert claim is not None
        assert claim.grab_held is False

    def test_round_trip(self) -> None:
        """to_json/from_json preserve the flag."""
        claim = Claim(**_BASE, grab="global", grab_held=True)
        assert Claim.from_json(claim.to_json()) == claim


class TestSetGrabHeld:
    """``Arbiter.set_grab_held`` rewrites the live claim in place."""

    def test_published_claim_starts_not_held(self, arb: Arbiter) -> None:
        """Published before the grab, so it must not claim one yet."""
        (claim,) = arb.live_claims()
        assert claim.grab_held is False

    def test_flip_is_visible_to_readers_and_back(self, arb: Arbiter) -> None:
        """True after the grab, False again on release, read off disk."""
        arb.set_grab_held(held=True)
        assert arb.claim.grab_held is True
        assert [c.grab_held for c in arb.live_claims()] == [True]
        arb.set_grab_held(held=False)
        assert [c.grab_held for c in arb.live_claims()] == [False]

    def test_rewrite_keeps_inode_and_flock(self, arb: Arbiter) -> None:
        """Same file, still locked: liveness stays the kernel's flock."""
        path = _claim_file(arb)
        inode = path.stat().st_ino
        for held in (True, False, True):
            arb.set_grab_held(held=held)
        assert path.stat().st_ino == inode
        with path.open("r", encoding="utf-8") as handle:
            with pytest.raises(BlockingIOError):
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            assert Claim.from_json(handle.read()) == arb.claim

    def test_another_process_sees_it_held(self, arb: Arbiter) -> None:
        """A separate process (the root enforcer, in production) reads it."""
        arb.set_grab_held(held=True)
        code = (
            "import sys; from pathlib import Path; from gatelock import held_grabs; "
            "print(len(held_grabs(Path(sys.argv[1]))))"
        )
        # Popen, not run: the suite-wide hermetic fixture patches subprocess.run.
        with subprocess.Popen(
            [sys.executable, "-c", code, str(arb._claims_dir)],
            stdout=subprocess.PIPE,
            text=True,
            env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
        ) as proc:
            stdout, _ = proc.communicate(timeout=20)
        assert stdout.strip() == "1"
        assert proc.returncode == 0

    def test_unchanged_value_does_not_touch_disk(self, arb: Arbiter) -> None:
        """Recovery reports every tick; only a transition is written."""
        with patch("gatelock._arbiter.rewrite_in_place") as rewrite:
            arb.set_grab_held(held=False)
            assert rewrite.call_count == 0
            arb.set_grab_held(held=True)
            written = rewrite.call_count
            arb.set_grab_held(held=True)
        assert written > 0
        assert rewrite.call_count == written

    def test_holder_file_follows_too(self, arb: Arbiter) -> None:
        """The holder.lock copy of the claim is kept in step."""
        assert arb.acquire_holder()
        arb.set_grab_held(held=True)
        holder = arb._root / "holder.lock"
        claim = Claim.from_json(holder.read_text(encoding="utf-8"))
        assert claim is not None
        assert claim.grab_held is True

    def test_unpublished_and_released_never_raise(self, tmp_path: Path) -> None:
        """No handle (or a closed one) is an in-memory update, not a crash."""
        arbiter = Arbiter("x", 1, grab="global", disable_vt=False, runtime_dir=tmp_path)
        arbiter.set_grab_held(held=True)
        assert arbiter.claim.grab_held is True
        arbiter.publish()
        arbiter.release()
        arbiter.set_grab_held(held=False)
        assert arbiter.claim.grab_held is False

    def test_a_closed_handle_is_logged_not_raised(
        self, arb: Arbiter, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A handle closed under us (ValueError) degrades to a warning."""
        assert arb._claim_handle is not None
        arb._claim_handle.close()
        arb.set_grab_held(held=True)
        assert "could not rewrite" in caplog.text


class TestHeldGrabs:
    """``held_grabs`` lists live claims whose grab is held right now."""

    def test_filters_unheld_and_grabless(self, tmp_path: Path) -> None:
        """Only a held, real grab counts."""
        runtime = tmp_path / "rt"
        held, unheld, grabless = (
            _arbiter(runtime, g) for g in ("global", "local", "none")
        )
        held.set_grab_held(held=True)
        grabless.set_grab_held(held=True)
        try:
            assert [c.instance_id for c in held_grabs(runtime / "claims")] == [
                held.claim.instance_id
            ]
        finally:
            for arbiter in (held, unheld, grabless):
                arbiter.release()

    def test_default_dir_is_the_runtime_claims_dir(self) -> None:
        """No argument reads the same dir Arbiter publishes into (hermetic env)."""
        arbiter = Arbiter("x", 1, grab="global", disable_vt=False)
        arbiter.publish()
        arbiter.set_grab_held(held=True)
        try:
            assert held_grabs() == (arbiter.claim,)
        finally:
            arbiter.release()
        assert held_grabs() == ()
