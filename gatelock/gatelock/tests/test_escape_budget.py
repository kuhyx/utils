"""Tests for the escape-hatch budget, lockout and recording.

Split from ``test_escape.py`` (250-line cap), which keeps policy defaults,
timestamp parsing, loading, and the integrity guarantee.
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
