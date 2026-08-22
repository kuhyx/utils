"""Tests for cross-app arbitration.

The strength-check table is the most important thing here: it is the invariant
that stops priority rank from becoming a way to disarm a stronger lock.
"""

from __future__ import annotations

import errno
import os
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from gatelock._arbiter import (
    RANK_SCREEN_LOCKER,
    RANK_WAKE_ALARM,
    Arbiter,
    Claim,
    _same_file,
    _try_lock,
    default_runtime_dir,
    grab_strength,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


DEFAULT_STARTED = "2026-07-25T12:00:00+00:00"


def dead_claim(app: str = "ghost", instance_id: str = "dead") -> Claim:
    """A claim belonging to a process that has since died."""
    return Claim(
        app=app,
        rank=RANK_WAKE_ALARM,
        pid=999999,
        started=DEFAULT_STARTED,
        grab="global",
        disable_vt=True,
        instance_id=instance_id,
    )


def make_claim(
    *,
    rank: int = RANK_SCREEN_LOCKER,
    started: str = DEFAULT_STARTED,
    grab: str = "global",
    disable_vt: bool = True,
) -> Claim:
    """A claim with sensible defaults."""
    return Claim(
        app="test_app",
        rank=rank,
        pid=1234,
        started=started,
        grab=grab,
        disable_vt=disable_vt,
        instance_id="tok",
    )


@pytest.fixture
def arb(tmp_path: Path) -> Iterator[Arbiter]:
    """A published hard-locking arbiter in an isolated runtime dir."""
    arbiter = Arbiter(
        "screen_locker",
        RANK_SCREEN_LOCKER,
        grab="global",
        disable_vt=True,
        runtime_dir=tmp_path / "rt",
    )
    arbiter.publish()
    yield arbiter
    arbiter.release()


def hard(name: str, rank: int, root: Path) -> Arbiter:
    """A hard-locking arbiter."""
    return Arbiter(name, rank, grab="global", disable_vt=True, runtime_dir=root)


class TestGrabStrength:
    """Unknown grab kinds must never rank as strong."""

    @pytest.mark.parametrize(
        ("kind", "expected"),
        [("none", 0), ("local", 1), ("global", 2), ("something-new", 0)],
    )
    def test_ordering(self, kind: str, expected: int) -> None:
        """Known kinds order none < local < global; unknown sorts weakest."""
        assert grab_strength(kind) == expected


class TestStrengthCheck:
    """THE anti-bypass invariant, as a table."""

    @pytest.mark.parametrize(
        ("their_grab", "their_vt", "our_grab", "our_vt", "strong_enough"),
        [
            ("global", True, "global", True, True),
            ("global", True, "local", False, True),
            ("global", True, "none", False, True),
            ("none", False, "global", True, False),
            ("local", True, "global", True, False),
            ("global", False, "global", True, False),
            ("local", False, "local", False, True),
            ("none", True, "none", True, True),
        ],
    )
    def test_table(
        self,
        their_grab: str,
        our_grab: str,
        *,
        their_vt: bool,
        our_vt: bool,
        strong_enough: bool,
    ) -> None:
        """Standing down requires being no weaker on BOTH axes."""
        theirs = make_claim(grab=their_grab, disable_vt=their_vt)
        ours = make_claim(grab=our_grab, disable_vt=our_vt)
        assert theirs.at_least_as_strong_as(ours) is strong_enough


class TestClaimSerialisation:
    """A malformed claim must never stop a locker arming."""

    def test_round_trip(self) -> None:
        """A claim survives serialisation."""
        claim = make_claim()
        assert Claim.from_json(claim.to_json()) == claim

    @pytest.mark.parametrize(
        "text", ["not json", "[]", '"a string"', "123", '{"app": "x"}']
    )
    def test_unusable_input_returns_none(self, text: str) -> None:
        """Bad JSON, wrong type, or missing fields all yield None."""
        assert Claim.from_json(text) is None

    def test_wrong_field_type_returns_none(self) -> None:
        """A non-numeric rank is rejected rather than raising."""
        assert (
            Claim.from_json(
                '{"app":"a","rank":"x","pid":1,"started":"s",'
                '"grab":"none","disable_vt":false,"instance_id":"t"}'
            )
            is None
        )

    def test_sort_key_orders_by_rank_then_start_then_pid(self) -> None:
        """Highest rank first, then earliest, then lowest pid."""
        high = make_claim(rank=300)
        low_early = make_claim(rank=100, started="2026-01-01T00:00:00+00:00")
        low_late = make_claim(rank=100, started="2026-12-01T00:00:00+00:00")
        ordered = sorted([low_late, high, low_early], key=Claim.sort_key)
        assert [c.rank for c in ordered] == [300, 100, 100]
        assert ordered[1] is low_early


class TestRuntimeDir:
    """Where claims live."""

    def test_env_override_wins(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """GATELOCK_RUNTIME_DIR takes precedence."""
        monkeypatch.setenv("GATELOCK_RUNTIME_DIR", str(tmp_path / "override"))
        assert default_runtime_dir() == tmp_path / "override"

    def test_xdg_runtime_dir(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Falls back to XDG_RUNTIME_DIR/gatelock."""
        monkeypatch.delenv("GATELOCK_RUNTIME_DIR", raising=False)
        monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "xdg"))
        assert default_runtime_dir() == tmp_path / "xdg" / "gatelock"

    def test_tempdir_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """With neither env var, a per-uid temp directory is used."""
        monkeypatch.delenv("GATELOCK_RUNTIME_DIR", raising=False)
        monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
        assert str(os.getuid()) in str(default_runtime_dir())


class TestTryLock:
    """flock wrapper behaviour."""

    def test_contended_returns_false(self, tmp_path: Path) -> None:
        """EAGAIN/EACCES mean somebody else holds it."""
        path = tmp_path / "f"
        path.write_text("x", encoding="utf-8")
        with path.open("r+", encoding="utf-8") as first:
            assert _try_lock(first) is True
            with path.open("r+", encoding="utf-8") as second:
                assert _try_lock(second) is False

    def test_other_oserror_propagates(self, tmp_path: Path) -> None:
        """An unexpected errno is a real problem and must not be swallowed."""
        path = tmp_path / "f"
        path.write_text("x", encoding="utf-8")
        with path.open("r+", encoding="utf-8") as handle:
            exc = OSError()
            exc.errno = errno.ENOSPC
            with (
                patch("gatelock._arbiter.fcntl.flock", side_effect=exc),
                pytest.raises(OSError, match=r"^$"),
            ):
                _try_lock(handle)

    def test_same_file_false_on_missing_path(self, tmp_path: Path) -> None:
        """A vanished path is not the same file."""
        path = tmp_path / "gone"
        path.write_text("x", encoding="utf-8")
        with path.open("r+", encoding="utf-8") as handle:
            path.unlink()
            assert _same_file(handle, path) is False
