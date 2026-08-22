"""Tests for the shared escape hatch.

The load-bearing property is that nothing here can ever *widen* the budget:
not a corrupt file, not an unparsable date, not a missing signing key.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from gatelock._escape import (
    EscapeDraft,
    EscapePolicy,
    EscapeTracker,
    _parse_iso,
    _today_iso,
)

if TYPE_CHECKING:
    from pathlib import Path

TODAY = "2026-07-25"
POLICY = EscapePolicy(name="sick", label="Sick")


@pytest.fixture
def key_file(tmp_path: Path) -> Path:
    """A throwaway signing key, so tests never touch the real root-owned one."""
    path = tmp_path / "hmac.key"
    path.write_bytes(b"0" * 32)
    return path


@pytest.fixture
def tracker(tmp_path: Path, key_file: Path) -> EscapeTracker:
    """A tracker over an empty history."""
    return EscapeTracker(POLICY, tmp_path / "escape.json", key_file=key_file)


def good_draft() -> EscapeDraft:
    """A justification that passes validation."""
    return EscapeDraft(
        reason="migraine", onset="03:00", severity=8, description="x" * 130
    )


class TestPolicyDefaults:
    """The defaults mirror screen-locker's proven sick mode."""

    def test_defaults(self) -> None:
        """Budgets, lockout and justification length match sick mode."""
        assert POLICY.budget_per_7_days == 1
        assert POLICY.budget_per_30_days == 3
        assert POLICY.budget_per_90_days == 10
        assert POLICY.lockout_seconds == 120
        assert POLICY.lockout_multiplier_per_recent == 2
        assert POLICY.justification_min_chars == 120


class TestParseIso:
    """Date parsing never guesses."""

    def test_valid(self) -> None:
        """A well-formed date parses."""
        parsed = _parse_iso(TODAY)
        assert parsed is not None
        assert parsed.year == 2026

    def test_invalid_returns_none(self) -> None:
        """Garbage is ignored rather than crashing the lock."""
        assert _parse_iso("not-a-date") is None

    def test_today_iso_round_trips(self) -> None:
        """The generated 'today' is parseable by the same parser."""
        assert _parse_iso(_today_iso()) is not None


class TestLoad:
    """Reading history, and what must never happen while doing so."""

    def test_missing_file(self, tracker: EscapeTracker) -> None:
        """No file yet means no uses."""
        assert tracker.load().used_days == []

    def test_corrupt_json(self, tracker: EscapeTracker, tmp_path: Path) -> None:
        """A truncated file degrades instead of raising."""
        (tmp_path / "escape.json").write_text("{not json", encoding="utf-8")
        assert tracker.load().used_days == []

    def test_unreadable_file(self, tracker: EscapeTracker, tmp_path: Path) -> None:
        """An unreadable file degrades instead of raising."""
        (tmp_path / "escape.json").write_text("{}", encoding="utf-8")
        with patch("pathlib.Path.read_text", side_effect=OSError("denied")):
            assert tracker.load().used_days == []

    def test_non_dict_payload(self, tracker: EscapeTracker, tmp_path: Path) -> None:
        """A JSON list is not a history."""
        (tmp_path / "escape.json").write_text("[]", encoding="utf-8")
        assert tracker.load().used_days == []

    def test_round_trip(self, tracker: EscapeTracker) -> None:
        """A recorded use survives a reload."""
        tracker.record(good_draft(), today=TODAY)
        reloaded = EscapeTracker(POLICY, tracker._path, key_file=tracker._key_file)
        reloaded.load()
        assert reloaded.history.used_days == [TODAY]
        assert reloaded.tampered == 0

    def test_non_dict_entries_are_skipped(
        self, tracker: EscapeTracker, tmp_path: Path
    ) -> None:
        """A stray scalar in the justification list is ignored."""
        (tmp_path / "escape.json").write_text(
            json.dumps({"used_days": [TODAY], "justifications": ["oops", 3]}),
            encoding="utf-8",
        )
        assert tracker.load().justifications == []

    def test_non_string_days_are_skipped(
        self, tracker: EscapeTracker, tmp_path: Path
    ) -> None:
        """A non-string date cannot count against the budget."""
        (tmp_path / "escape.json").write_text(
            json.dumps({"used_days": [TODAY, 7], "justifications": []}),
            encoding="utf-8",
        )
        assert tracker.load().used_days == [TODAY]


class TestIntegrityNeverWidensTheBudget:
    """The anti-bypass property of this module."""

    def test_tampered_entry_is_kept_and_reported(self, tracker: EscapeTracker) -> None:
        """Editing the file is shouted about -- and still counts against you."""
        tracker.record(good_draft(), today=TODAY)
        raw = json.loads(tracker._path.read_text(encoding="utf-8"))
        raw["justifications"][0]["description"] = "actually I just felt like it"
        tracker._path.write_text(json.dumps(raw), encoding="utf-8")

        reloaded = EscapeTracker(POLICY, tracker._path, key_file=tracker._key_file)
        reloaded.load()

        assert reloaded.tampered == 1
        # The crucial bit: the edit did NOT buy back any budget.
        assert reloaded.history.used_days == [TODAY]
        assert reloaded.is_budget_exhausted(today=TODAY) is True

    def test_unreadable_key_does_not_reset_the_budget(
        self, tracker: EscapeTracker, tmp_path: Path
    ) -> None:
        """chmod-ing the signing key must not become an unlimited hatch."""
        tracker.record(good_draft(), today=TODAY)
        missing = tmp_path / "gone.key"

        reloaded = EscapeTracker(POLICY, tracker._path, key_file=missing)
        reloaded.load()

        assert reloaded.tampered == 1
        assert reloaded.is_budget_exhausted(today=TODAY) is True

    def test_unsigned_entry_still_counts(
        self, tracker: EscapeTracker, tmp_path: Path
    ) -> None:
        """An entry with no signature at all is still a use."""
        (tmp_path / "escape.json").write_text(
            json.dumps({"used_days": [TODAY], "justifications": [{"date": TODAY}]}),
            encoding="utf-8",
        )
        tracker.load()
        assert tracker.tampered == 1
        assert tracker.is_budget_exhausted(today=TODAY) is True
