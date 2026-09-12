# Copyright (c) 2026 Krzysztof Rudnicki
"""The audit trail: best-effort, signed, and never in the way."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
import json
from typing import TYPE_CHECKING

from freedays._audit import record_event
from freedays._hmac import verify
from freedays._paths import Paths

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


DAY = date(2026, 12, 24)


def _lines(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_an_event_is_appended_with_its_details(state_dir: Path) -> None:
    record_event("mark", DAY, actor="device-1", reason="wedding")
    (entry,) = _lines(state_dir / "audit.jsonl")
    assert entry["action"] == "mark"
    assert entry["day"] == "2026-12-24"
    assert entry["actor"] == "device-1"
    assert entry["reason"] == "wedding"


def test_events_accumulate_rather_than_overwrite(state_dir: Path) -> None:
    record_event("mark", DAY, actor="device-1")
    record_event("release", DAY, actor="device-1")
    assert len(_lines(state_dir / "audit.jsonl")) == 2


def test_the_signing_key_is_generated_on_first_use(state_dir: Path) -> None:
    key = state_dir / "hmac.key"
    assert not key.exists()
    record_event("mark", DAY, actor="device-1")
    assert key.exists()


def test_the_written_entry_verifies_against_the_key(state_dir: Path) -> None:
    record_event("mark", DAY, actor="device-1")
    (entry,) = _lines(state_dir / "audit.jsonl")
    assert verify(entry, key_file=state_dir / "hmac.key")


def test_a_tampered_entry_stops_verifying(state_dir: Path) -> None:
    record_event("mark", DAY, actor="device-1")
    (entry,) = _lines(state_dir / "audit.jsonl")
    entry["day"] = "2026-12-25"
    assert not verify(entry, key_file=state_dir / "hmac.key")


def test_an_existing_key_is_reused_rather_than_regenerated(state_dir: Path) -> None:
    record_event("mark", DAY, actor="device-1")
    original = (state_dir / "hmac.key").read_bytes()
    record_event("release", DAY, actor="device-1")
    assert (state_dir / "hmac.key").read_bytes() == original


def test_explicit_paths_are_honoured(tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere"
    record_event("mark", DAY, actor="device-1", paths=Paths.under(elsewhere))
    (entry,) = _lines(elsewhere / "audit.jsonl")
    assert verify(entry, key_file=elsewhere / "hmac.key")


def test_an_unwritable_trail_warns_but_never_raises(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A day must be takeable even when its audit line cannot be written."""
    blocked = tmp_path / "a-file" / "audit.jsonl"
    blocked.parent.write_text("I am a file, not a directory", encoding="utf-8")
    with caplog.at_level("WARNING"):
        record_event(
            "mark",
            DAY,
            actor="device-1",
            paths=replace(Paths.under(tmp_path), audit=blocked),
        )
    assert "could not append" in caplog.text
