# Copyright (c) 2026 Krzysztof Rudnicki
"""Timeline builder: telemetry entries -> recording timestamps."""

import json
from typing import TYPE_CHECKING, Any

import pytest

from game_recording import timeline
from game_recording.tests.test_helpers import MOMENT_MAP, SESSION, SYNC_MS, SYNC_UNIX, entry, sync_entry

if TYPE_CHECKING:
    from pathlib import Path

    from game_recording.config import Moment, Row

# The recorder started 0.5 s after the game's sync instant (t0 on the unix clock).
T0 = SYNC_UNIX + 0.5
VIDEO_START_S = 0.052
ORDER: dict[str, Any] = {"order": "rally", "pos": [1, 2]}


def one_part(start_s: float = VIDEO_START_S, duration_s: float = 600.0) -> list[dict[str, Any]]:
    """A single unnamed part file, as one uninterrupted recording."""
    return [{"file": "", "start_s": start_s, "duration_s": duration_s}]


def build(entries: list[Row], parts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return timeline.build_events(
        entries,
        session=SESSION,
        t0_unix=T0,
        parts=parts or one_part(),
        moment_map=MOMENT_MAP,
    )


def kinds(doc: dict[str, Any]) -> list[str]:
    return [e["kind"] for e in doc["events"]]


def command(ms_after_sync: int, seq: int = 2) -> Row:
    return entry("command", SYNC_MS + ms_after_sync, seq, **ORDER)


def test_event_time_is_sync_unix_plus_ms_delta_minus_t0() -> None:
    # event 5000 ms after the sync entry -> unix SYNC+5.0 -> 4.5 s after t0
    doc = build([sync_entry(), command(5000)])
    order = next(e for e in doc["events"] if e["kind"] == "command")
    assert order["t"] == pytest.approx(4.5, abs=1e-6)


def test_offset_is_exact_to_a_millisecond() -> None:
    doc = build([sync_entry(), command(1234)])
    order = next(e for e in doc["events"] if e["kind"] == "command")
    assert order["t"] == pytest.approx(1.234 - 0.5, abs=1e-3)


def test_unix_us_integer_microseconds_is_read() -> None:
    sync = {**sync_entry(), "unix_us": round(SYNC_UNIX * 1_000_000)}
    del sync["unix"]
    doc = build([sync, command(5000)])
    assert doc["events"][0]["t"] == pytest.approx(4.5, abs=1e-6)


def test_sync_entry_itself_is_not_a_moment() -> None:
    assert "recording_sync" not in kinds(build([sync_entry()]))


def test_events_before_the_recorder_started_are_flagged_not_dropped() -> None:
    doc = build([sync_entry(), entry("game_start", SYNC_MS + 100, 2, game="watch")])
    start = next(e for e in doc["events"] if e["kind"] == "game_start")
    assert start["t"] < VIDEO_START_S
    assert start["before_recording"]


def test_events_after_the_file_ended_are_flagged() -> None:
    doc = build([sync_entry(), command(700_000)], parts=one_part(duration_s=10.0))
    assert doc["events"][-1]["after_recording"]


def test_no_sync_entry_falls_back_to_wall_time_and_says_so() -> None:
    doc = build([entry("session_start", 0, 1), entry("command", 3000, 2, **ORDER)])
    assert doc["sync"]["approx"]
    assert doc["sync"]["method"] == "session_start.time"


@pytest.mark.parametrize(
    "rows",
    [[], [{"event": "session_start", "ms": 0}], [{"event": "recording_sync", "ms": 5}]],
)
def test_no_usable_sync_entry_is_an_error(rows: list[Row]) -> None:
    with pytest.raises(timeline.NoSyncError):
        timeline.find_sync(rows)


def test_sync_is_a_value_with_keyword_approx() -> None:
    sync = timeline.find_sync([sync_entry()])
    assert sync == timeline.Sync(SYNC_UNIX, SYNC_MS, "recording_sync", approx=False)


def test_exact_sync_is_not_approx() -> None:
    doc = build([sync_entry()])
    assert not doc["sync"]["approx"]
    assert doc["sync"]["method"] == "recording_sync"


def test_other_sessions_are_ignored() -> None:
    other = {**entry("command", 9000, 5, **ORDER), "session": "someone-else"}
    assert "command" not in kinds(build([sync_entry(), other]))


def test_events_are_sorted_by_time() -> None:
    rows = [sync_entry(), entry("pause_open", 9000, 3), entry("pause_close", 4000, 2)]
    times = [e["t"] for e in build(rows)["events"]]
    assert times == sorted(times)


def test_the_tag_comes_from_the_first_entry_that_has_one() -> None:
    assert build([sync_entry()])["tag"] == ""
    assert build([sync_entry(), entry("hub_open", 300, 2, tag="v01")])["tag"] == "v01"


def meta(rows: list[Row]) -> str:
    doc = build([sync_entry(), *rows])
    return timeline.chapters_ffmetadata(doc["events"], duration_s=600.0, video_start_s=VIDEO_START_S)


def test_events_in_the_same_millisecond_share_one_chapter() -> None:
    # the muxer drops a second chapter with the same start
    text = meta(
        [
            entry("pause_open", SYNC_MS + 10_500, 2),
            entry("reset_progress", SYNC_MS + 10_500, 3, files=2),
            entry("pause_close", SYNC_MS + 12_500, 4),
        ]
    )
    assert text.count("[CHAPTER]") == 2
    title = next(line for line in text.splitlines() if line.startswith("title=pause_open"))
    assert "reset_progress" in title


def test_header_and_chapter_block() -> None:
    lines = meta([command(10_500)]).splitlines()
    assert lines[0] == ";FFMETADATA1"
    assert "[CHAPTER]" in lines
    assert "TIMEBASE=1/1000" in lines
    assert "START=10000" in lines
    assert any(line.startswith("title=") for line in lines)


def test_chapters_do_not_overlap_and_end_at_the_next_start() -> None:
    lines = meta([command(5500), entry("pause_open", SYNC_MS + 9500, 3)]).splitlines()
    starts = [int(x.split("=")[1]) for x in lines if x.startswith("START=")]
    ends = [int(x.split("=")[1]) for x in lines if x.startswith("END=")]
    assert starts == [5000, 9000]
    assert ends[0] == starts[1] - 1
    assert ends[1] >= starts[1]


def test_events_outside_the_file_get_no_chapter() -> None:
    assert "[CHAPTER]" not in meta([entry("game_start", SYNC_MS + 100, 2, game="watch")])


def test_titles_escape_ffmetadata_specials() -> None:
    assert timeline.escape_meta("a=b;c#d\\e\nf") == "a\\=b\\;c\\#d\\\\e\\\nf"


def test_load_session_reads_only_that_session(tmp_path: Path) -> None:
    other = {**entry("command", 1, 1, **ORDER), "session": "other"}
    path = tmp_path / "feedback.jsonl"
    rows = [sync_entry(), other, entry("pause_open", 9000, 3)]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\nnot json\n[1]\n", encoding="utf-8")
    loaded = timeline.load_session(path, SESSION)
    assert [r["event"] for r in loaded] == ["recording_sync", "pause_open"]


def test_document_is_json_serialisable() -> None:
    doc = build([sync_entry(), command(9000)])
    assert json.loads(json.dumps(doc))["session"] == SESSION


# The recorder restarts when the window goes away (workspace switch): one part per run.
PARTS: list[dict[str, Any]] = [
    {"file": "s.mkv", "start_s": 0.05, "duration_s": 10.0},
    {"file": "s.part2.mkv", "start_s": 20.0, "duration_s": 10.0},
]


def parts_doc(ms_after_sync: int) -> dict[str, Any]:
    return build([sync_entry(), command(ms_after_sync)], parts=PARTS)


def parts_event(t: float) -> Moment:
    # t seconds on the file timeline <-> ms in the game clock (t0 is 0.5 s after the sync)
    return next(e for e in parts_doc(round((t + 0.5) * 1000))["events"] if e["kind"] == "command")


def test_event_in_a_part_names_that_file() -> None:
    assert parts_event(5.0)["file"] == "s.mkv"
    assert parts_event(25.0)["file"] == "s.part2.mkv"


def test_event_between_the_parts_is_flagged_in_gap() -> None:
    event = parts_event(15.0)
    assert event["in_gap"]
    assert "file" not in event
    assert not timeline.in_recording(event)


def test_before_the_first_and_after_the_last_part() -> None:
    assert parts_event(0.0)["before_recording"]
    assert parts_event(40.0)["after_recording"]


def test_event_in_an_unnamed_part_has_no_file() -> None:
    event = build([sync_entry(), command(5000)])["events"][0]
    assert "file" not in event
    assert timeline.in_recording(event)


def test_document_lists_the_parts_and_the_overall_span() -> None:
    video = parts_doc(6000)["video"]
    assert [p["file"] for p in video["parts"]] == ["s.mkv", "s.part2.mkv"]
    assert (video["start_s"], video["end_s"]) == (0.05, 30.0)


def test_chapters_are_per_part() -> None:
    doc = parts_doc(25_500)
    text = timeline.chapters_ffmetadata(doc["events"], 10.0, 20.0, file="s.part2.mkv")
    assert "START=25000" in text
    assert "[CHAPTER]" not in timeline.chapters_ffmetadata(doc["events"], 10.0, 0.05, file="s.mkv")
