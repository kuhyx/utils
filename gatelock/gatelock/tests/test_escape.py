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


class TestBudget:
    """Rolling windows."""

    def test_counts_only_inside_the_window(self, tracker: EscapeTracker) -> None:
        """An old use falls out of the 7-day window."""
        tracker.history.used_days = ["2026-07-24", "2026-06-01"]
        assert tracker.count_in_window(7, today=TODAY) == 1
        assert tracker.count_in_window(90, today=TODAY) == 2

    def test_unparsable_today_counts_nothing(self, tracker: EscapeTracker) -> None:
        """A broken 'today' cannot silently exhaust the budget."""
        tracker.history.used_days = [TODAY]
        assert tracker.count_in_window(7, today="garbage") == 0

    def test_unparsable_entry_is_skipped(self, tracker: EscapeTracker) -> None:
        """A corrupt stored date is ignored, loudly."""
        tracker.history.used_days = ["nonsense", TODAY]
        assert tracker.count_in_window(7, today=TODAY) == 1

    @pytest.mark.parametrize(
        ("days", "expected"),
        [(["2026-07-25"], True), ([], False)],
    )
    def test_week_window(
        self, tracker: EscapeTracker, days: list[str], *, expected: bool
    ) -> None:
        """One use exhausts the weekly budget of 1."""
        tracker.history.used_days = days
        assert tracker.is_budget_exhausted(today=TODAY) is expected

    def test_month_window(self, tracker: EscapeTracker) -> None:
        """Three uses in 30 days exhausts, even if none is in the last week."""
        tracker.history.used_days = ["2026-07-05", "2026-07-06", "2026-07-07"]
        assert tracker.is_budget_exhausted(today=TODAY) is True

    def test_quarter_window(self, tracker: EscapeTracker) -> None:
        """Ten uses in 90 days exhausts, spread out enough to clear the others."""
        tracker.history.used_days = [f"2026-05-{day:02d}" for day in range(1, 11)]
        assert tracker.is_budget_exhausted(today=TODAY) is True

    def test_nothing_used_is_not_exhausted(self, tracker: EscapeTracker) -> None:
        """A clean history leaves the hatch available."""
        assert tracker.is_budget_exhausted(today=TODAY) is False


class TestLockout:
    """The wait grows the more you lean on the hatch."""

    @pytest.mark.parametrize(
        ("recent", "seconds"), [(0, 120), (1, 240), (2, 480), (3, 960)]
    )
    def test_doubles_per_recent_use(
        self, tracker: EscapeTracker, recent: int, seconds: int
    ) -> None:
        """base * 2 ** uses_in_30_days."""
        tracker.history.used_days = [f"2026-07-{10 + i:02d}" for i in range(recent)]
        assert tracker.compute_lockout_seconds(today=TODAY) == seconds


class TestValidation:
    """What counts as a real justification."""

    def test_accepts_a_proper_one(self, tracker: EscapeTracker) -> None:
        """A complete draft passes."""
        assert tracker.validate(good_draft()) is None

    @pytest.mark.parametrize(
        ("draft", "fragment"),
        [
            (EscapeDraft("", "03:00", 5, "x" * 130), "what the problem is"),
            (EscapeDraft("flu", "", 5, "x" * 130), "when it started"),
            (EscapeDraft("flu", "03:00", 0, "x" * 130), "between 1 and 10"),
            (EscapeDraft("flu", "03:00", 11, "x" * 130), "between 1 and 10"),
            (EscapeDraft("flu", "03:00", 5, "short"), "Explain properly"),
        ],
    )
    def test_rejections(
        self, tracker: EscapeTracker, draft: EscapeDraft, fragment: str
    ) -> None:
        """Each missing or lazy field is refused with a specific complaint."""
        message = tracker.validate(draft)
        assert message is not None
        assert fragment in message


class TestRecord:
    """Writing a use down."""

    def test_records_and_signs(self, tracker: EscapeTracker) -> None:
        """A use is appended, dated and signed."""
        assert tracker.record(good_draft(), today=TODAY) is True
        entry = tracker.history.justifications[-1]
        assert entry["date"] == TODAY
        assert entry["policy"] == "sick"
        assert "hmac" in entry

    def test_unsigned_when_key_unavailable(
        self, tracker: EscapeTracker, tmp_path: Path
    ) -> None:
        """Without a key the entry is still recorded, just unsigned."""
        tracker._key_file = tmp_path / "absent.key"
        assert tracker.record(good_draft(), today=TODAY) is True
        assert "hmac" not in tracker.history.justifications[-1]

    def test_same_day_twice_counts_once(self, tracker: EscapeTracker) -> None:
        """Two uses on one day are one day of budget."""
        tracker.record(good_draft(), today=TODAY)
        tracker.record(good_draft(), today=TODAY)
        assert tracker.history.used_days == [TODAY]
        assert len(tracker.history.justifications) == 2

    def test_uses_today_when_unspecified(self, tracker: EscapeTracker) -> None:
        """Omitting the date records the real today."""
        tracker.record(good_draft())
        assert tracker.history.used_days == [_today_iso()]

    def test_save_failure_is_reported(self, tracker: EscapeTracker) -> None:
        """A read-only disk is surfaced, not swallowed."""
        with patch("pathlib.Path.write_text", side_effect=OSError("ro")):
            assert tracker.record(good_draft(), today=TODAY) is False


class TestReadBack:
    """Showing past excuses back to the user is half the deterrent."""

    def test_empty(self, tracker: EscapeTracker) -> None:
        """A clean history says so."""
        assert tracker.format_recent() == "(no previous uses)"
        assert tracker.recent_justifications() == []

    def test_lists_recent(self, tracker: EscapeTracker) -> None:
        """Past entries are rendered with date, severity and reason."""
        tracker.record(good_draft(), today=TODAY)
        rendered = tracker.format_recent()
        assert TODAY in rendered
        assert "8/10" in rendered
        assert "migraine" in rendered

    def test_respects_explicit_limit(self, tracker: EscapeTracker) -> None:
        """An explicit count overrides the policy default."""
        for day in range(1, 6):
            tracker.record(good_draft(), today=f"2026-07-{day:02d}")
        assert len(tracker.recent_justifications(2)) == 2

    def test_handles_entries_missing_fields(
        self, tracker: EscapeTracker, tmp_path: Path
    ) -> None:
        """A partial entry renders without raising."""
        (tmp_path / "escape.json").write_text(
            json.dumps({"used_days": [], "justifications": [{}]}), encoding="utf-8"
        )
        tracker.load()
        assert "?" in tracker.format_recent()


class TestSummary:
    """The one-line budget readout."""

    def test_summary_shows_all_three_windows(self, tracker: EscapeTracker) -> None:
        """Week, month and quarter counts all appear."""
        tracker.history.used_days = [TODAY]
        assert tracker.budget_summary(today=TODAY) == "Sick: 1/1w · 1/3m · 1/10q"

    def test_policy_property(self, tracker: EscapeTracker) -> None:
        """The tracker exposes the policy it enforces."""
        assert tracker.policy is POLICY
