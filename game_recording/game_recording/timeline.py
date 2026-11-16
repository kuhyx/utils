# Copyright (c) 2026 Krzysztof Rudnicki
"""Telemetry entries -> timestamps on the recording's timeline (events.json, chapters).

The game's entries carry `ms` since its log opened. One `recording_sync` entry
pairs an `ms` with the unix time of that same instant, so every entry has an
exact wall-clock time. The recorder's start (`t0_unix`) is on the same unix
clock (ffmpeg's -output_ts_offset puts its media timeline at t0), hence

    t = sync.unix + (entry.ms - sync.ms) / 1000 - t0_unix

`t` is seconds on the file's media timeline: what mpv shows with
`--rebase-start-time=no` and where MKV chapters sit. The first frame is at
`video_start_s` (a few tens of ms after t0), so earlier events are flagged
`before_recording`, later ones `after_recording`.

The recorder restarts when the game's window goes away and comes back (an i3
workspace switch): one part file per run, all on the same t0 timeline. An event
between two parts is `in_gap`; every other recorded event names its `file`.
"""

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from game_recording import moments

if TYPE_CHECKING:
    from game_recording.config import Moment, MomentMap, Row


class NoSyncError(ValueError):
    """The session has neither a recording_sync nor a session_start entry."""


@dataclass(frozen=True)
class Sync:
    """One pairing of the game clock (`ms`) with unix time."""

    unix_s: float
    ms: int
    method: str
    approx: bool


def load_session(path: Path, session: str) -> list[Row]:
    """The entries of one session from a feedback.jsonl (bad lines are skipped)."""
    rows: list[Row] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("session") == session:
            rows.append(row)
    return rows


def find_sync(entries: list[Row]) -> Sync:
    """The exact pairing from recording_sync, else session_start's whole-second `time`."""
    for row in entries:
        if row.get("event") == "recording_sync" and ("unix_us" in row or "unix" in row):
            unix = row["unix_us"] / 1_000_000 if "unix_us" in row else float(row["unix"])
            return Sync(unix, int(row["ms"]), "recording_sync", approx=False)
    for row in entries:
        if row.get("event") == "session_start" and "time" in row:
            wall = datetime.fromisoformat(row["time"]).timestamp()
            return Sync(wall, int(row.get("ms", 0)), "session_start.time", approx=True)
    msg = "no recording_sync or session_start entry"
    raise NoSyncError(msg)


def _flag(moment: Moment, t: float, parts: list[dict[str, Any]]) -> None:
    """Names the part file the moment is in, or says why it is in none."""
    for part in parts:
        if part["start_s"] - 1e-6 <= t <= part["start_s"] + part["duration_s"] + 1e-6:
            if part["file"]:
                moment["file"] = part["file"]
            return
    if t < parts[0]["start_s"]:
        moment["before_recording"] = True
    elif t > parts[-1]["start_s"] + parts[-1]["duration_s"]:
        moment["after_recording"] = True
    else:
        moment["in_gap"] = True


def build_events(
    entries: list[Row],
    *,
    session: str,
    t0_unix: float,
    parts: list[dict[str, Any]],
    moment_map: MomentMap,
) -> dict[str, Any]:
    """The events.json document for one recording (`parts`: file, start_s, duration_s per part file)."""
    rows = [r for r in entries if r.get("session") == session]
    sync = find_sync(rows)
    first, last = parts[0]["start_s"], parts[-1]["start_s"] + parts[-1]["duration_s"]
    found = moments.classify(rows, moment_map)
    found += moments.derive(rows, moment_map)
    events = []
    for moment in found:
        t = sync.unix_s + (moment["ms"] - sync.ms) / 1000 - t0_unix
        moment["t"] = round(t, 6)
        _flag(moment, t, parts)
        events.append(moment)
    events.sort(key=lambda m: (m["t"], m.get("seq") or 0))
    tag = next((r["tag"] for r in rows if "tag" in r), "")
    return {
        "session": session,
        "tag": tag,
        "t0_unix": t0_unix,
        "video": {"start_s": first, "duration_s": last - first, "end_s": last, "parts": parts},
        "sync": {"method": sync.method, "approx": sync.approx, "unix": sync.unix_s, "ms": sync.ms},
        "events": events,
    }


def in_recording(event: Moment) -> bool:
    """True when the moment sits inside a recorded part (not before, after or in a gap)."""
    return not (event.get("before_recording") or event.get("after_recording") or event.get("in_gap"))


def escape_meta(text: str) -> str:
    r"""Escape for ffmetadata: backslash-prefix = ; # \ and newline."""
    return "".join("\\" + c if c in "=;#\\\n" else c for c in text)


def chapters_ffmetadata(events: list[Moment], duration_s: float, video_start_s: float, file: str | None = None) -> str:
    """An ffmetadata file with one chapter per event that lies inside the file (the part `file`)."""
    inside = [e for e in events if in_recording(e) and (file is None or e.get("file", file) == file)]
    end_ms = round((video_start_s + duration_s) * 1000)
    # The muxer drops a second chapter with the same start: events of one millisecond share one.
    titles: dict[int, list[str]] = {}
    for event in inside:
        titles.setdefault(round(event["t"] * 1000), []).append(event["label"])
    starts = list(titles)
    lines = [";FFMETADATA1"]
    for i, start in enumerate(starts):
        nxt = starts[i + 1] - 1 if i + 1 < len(starts) else end_ms
        lines += [
            "[CHAPTER]",
            "TIMEBASE=1/1000",
            f"START={start}",
            f"END={max(start, nxt)}",
            f"title={escape_meta(' | '.join(titles[start]))}",
        ]
    return "\n".join(lines) + "\n"
