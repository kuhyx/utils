# Copyright (c) 2026 Krzysztof Rudnicki
"""After the game exits: events.json, chapters remuxed in, no re-encode."""

import json
import subprocess
from typing import TYPE_CHECKING, Any

import pytest

from game_recording import finalize
from game_recording.tests.test_helpers import MOMENT_MAP, SESSION, SYNC_MS, SYNC_UNIX, entry, sync_entry

if TYPE_CHECKING:
    from pathlib import Path

T0 = SYNC_UNIX + 0.5
START = 0.052


def make_video(path: Path) -> None:
    """A 4 s test pattern + tone whose timeline starts at START (like the real recorder's)."""
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=30"]
    cmd += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "4"]
    cmd += ["-output_ts_offset", str(START), "-c:v", "libx264", "-c:a", "flac", str(path)]
    subprocess.run(cmd, check=True, timeout=30)


def ffprobe(*args: str) -> dict[str, Any]:
    cmd = ["ffprobe", "-v", "error", "-of", "json", *args]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True)
    probed: dict[str, Any] = json.loads(out.stdout)
    return probed


def write_meta(root: Path, rec: Path, extra: dict[str, object]) -> Path:
    """A rec.json for a single video file next to the feedback log."""
    meta = {
        "session": SESSION,
        "t0_unix": T0,
        "video": f"{SESSION}.mkv",
        "feedback": str(root / "feedback.jsonl"),
        **extra,
    }
    path = rec / f"{SESSION}.rec.json"
    path.write_text(json.dumps(meta), encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def session(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, Any]]:
    root = tmp_path_factory.mktemp("session")
    rec = root / "recordings"
    rec.mkdir()
    make_video(rec / f"{SESSION}.mkv")
    rows = [
        sync_entry(),
        entry("game_start", SYNC_MS + 100, 2, game="watch"),
        entry("command", SYNC_MS + 1500, 3, order="rally", pos=[1, 2]),
        entry("buy", SYNC_MS + 2500, 4, buff="stew", bought=True, cost=1),
        entry("game_end", SYNC_MS + 3300, 5, game="watch", outcome="lose", elapsed_s=3.2),
    ]
    (root / "feedback.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    meta_path = write_meta(root, rec, {"encoder": "libx264"})
    return rec, finalize.finalize(meta_path, MOMENT_MAP)


def test_events_json_is_written_with_timestamps_inside_the_duration(session: tuple[Path, dict[str, Any]]) -> None:
    rec, doc = session
    written = json.loads((rec / f"{SESSION}.events.json").read_text(encoding="utf-8"))
    assert written["events"] == doc["events"]
    assert written["video"]["encoder"] == "libx264"
    assert written["video"]["file"] == f"{SESSION}.mkv"
    end = written["video"]["end_s"]
    inside = [e for e in written["events"] if not e.get("before_recording")]
    assert inside
    for event in inside:
        assert START - 1e-3 <= event["t"] <= end + 1e-3


def test_video_start_and_duration_come_from_the_file(session: tuple[Path, dict[str, Any]]) -> None:
    doc = session[1]
    assert doc["video"]["start_s"] == pytest.approx(START, abs=1e-2)
    assert doc["video"]["duration_s"] > 3.5


def test_chapters_are_embedded_without_reencoding_or_moving_the_timeline(
    session: tuple[Path, dict[str, Any]],
) -> None:
    rec, doc = session
    info = ffprobe("-show_chapters", "-show_streams", str(rec / f"{SESSION}.mkv"))
    starts = [float(c["start_time"]) for c in info["chapters"]]
    expected = [e["t"] for e in doc["events"] if not e.get("before_recording")]
    assert len(starts) == len(expected)
    for got, want in zip(starts, expected, strict=True):
        assert got == pytest.approx(want, abs=1e-2)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert video["codec_name"] == "h264"
    assert float(video["start_time"]) == pytest.approx(START, abs=1e-2)
    assert not (rec / f"{SESSION}.ffmeta").exists()


def test_first_run_game_start_before_the_recorder_is_flagged(session: tuple[Path, dict[str, Any]]) -> None:
    start = next(e for e in session[1]["events"] if e["kind"] == "game_start")
    assert start.get("before_recording")


def test_finalize_is_repeatable(session: tuple[Path, dict[str, Any]]) -> None:
    rec, doc = session
    again = finalize.finalize(rec / f"{SESSION}.rec.json", MOMENT_MAP)
    assert [e["t"] for e in again["events"]] == [e["t"] for e in doc["events"]]


def test_a_file_without_a_duration_is_scanned_whole(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    video = tmp_path / "open.mkv"
    make_video(video)
    real = finalize._ffprobe

    def fake(*args: str) -> dict[str, Any]:
        return {"format": {"start_time": "0.5"}} if "format=start_time,duration" in args else real(*args)

    monkeypatch.setattr(finalize, "_ffprobe", fake)
    start, duration = finalize.probe_span(video)
    assert start == 0.5
    assert duration > 3.0


def test_a_file_without_packets_has_no_duration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(*args: str) -> dict[str, Any]:
        return {"format": {"start_time": "0.5"}} if "format=start_time,duration" in args else {"packets": [{}]}

    monkeypatch.setattr(finalize, "_ffprobe", fake)
    assert finalize.probe_span(tmp_path / "x.mkv") == (0.5, 0.0)


def test_a_first_frame_for_a_missing_part_is_ignored(tmp_path: Path) -> None:
    (tmp_path / "feedback.jsonl").write_text(json.dumps(sync_entry()) + "\n", encoding="utf-8")
    make_video(tmp_path / f"{SESSION}.mkv")
    meta = write_meta(tmp_path, tmp_path, {"first_frame_unix": {"gone.mkv": T0}})
    assert finalize.finalize(meta, MOMENT_MAP)["video"]["start_s"] == pytest.approx(START, abs=1e-2)


def test_an_unaligned_gsr_part_is_moved_once_and_stays_put(tmp_path: Path) -> None:
    """A gsr part starts at 0; rec.json says when its first frame was, finalize puts it on the t0 timeline."""
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=30", "-t", "2"]
    subprocess.run([*cmd, "-c:v", "libx264", str(tmp_path / f"{SESSION}.mkv")], check=True, timeout=30)
    (tmp_path / "feedback.jsonl").write_text(json.dumps(sync_entry()) + "\n", encoding="utf-8")
    meta = write_meta(tmp_path, tmp_path, {"first_frame_unix": {f"{SESSION}.mkv": T0 + 2.0}})
    for _ in range(2):
        doc = finalize.finalize(meta, MOMENT_MAP)
        assert doc["video"]["start_s"] == pytest.approx(2.0, abs=1e-2)
