# Copyright (c) 2026 Krzysztof Rudnicki
"""Lists recordings and opens one at a moment (the code behind scripts/recordings.sh)."""

import json
import shlex
import subprocess
import sys
from typing import TYPE_CHECKING, Any

from game_recording import timeline

if TYPE_CHECKING:
    from pathlib import Path

type Doc = dict[str, Any]
LEAD_S = 3.0  # open this long before the moment, so the cause is on screen


def stamp(seconds: float) -> str:
    """mm:ss.mmm of a time on the recording's timeline."""
    sign = "-" if seconds < 0 else ""
    millis = round(abs(seconds) * 1000)
    return f"{sign}{millis // 60000:02d}:{millis // 1000 % 60:02d}.{millis % 1000:03d}"


def sessions(rec_dir: Path) -> list[Path]:
    """events.json files, newest first."""
    return sorted(rec_dir.glob("*.events.json"), key=lambda p: p.stat().st_mtime, reverse=True)


def load(path: Path) -> Doc:
    """One events.json document."""
    doc: Doc = json.loads(path.read_text(encoding="utf-8"))
    return doc


def shown(doc: Doc) -> list[Doc]:
    """The moments inside a recording part, in the numbering `open <n>` uses (1-based)."""
    return [e for e in doc["events"] if timeline.in_recording(e)]


def table(doc: Doc) -> str:
    """One recording as text: a header line, notes, then its numbered moments."""
    video = doc["video"]
    lines = [f"{doc['session']}  {doc.get('tag', '')}  {stamp(video['duration_s'])}  {video.get('file', '')}"]
    if len(video.get("parts", [])) > 1:
        spans = ", ".join(
            f"{p['file']} {stamp(p['start_s'])}-{stamp(p['start_s'] + p['duration_s'])}" for p in video["parts"]
        )
        lines.append(f"note: the window went away; {len(video['parts'])} parts: {spans}")
    if doc["sync"]["approx"]:
        lines.append("note: clocks synced from a whole-second wall time (build without recording_sync), +-1 s")
    for n, event in enumerate(shown(doc), 1):
        png = f"  {event['png']}" if event.get("png") else ""
        part = f"  [{event['file']}]" if event.get("file") and event["file"] != video.get("file") else ""
        lines.append(f"{n:3d}  {stamp(event['t'])}  {event['label']}{png}{part}")
    return "\n".join(lines)


def listing(rec_dir: Path) -> str:
    """One line per recording, newest first."""
    out = []
    for path in sessions(rec_dir):
        doc = load(path)
        out.append(
            f"{doc['session']}  {stamp(doc['video']['duration_s'])}  {len(shown(doc))} moments  {doc.get('tag', '')}"
        )
    return "\n".join(out)


def open_command(doc: Doc, rec_dir: Path, n: int | None) -> list[str]:
    """Mpv argv at moment n (None = from the start). --rebase-start-time=no keeps mpv on the file's own timeline."""
    parts = doc["video"].get("parts") or [{"file": doc["video"]["file"], "start_s": doc["video"]["start_s"]}]
    name, first_frame = doc["video"]["file"], parts[0]["start_s"]
    cmd = ["mpv", "--rebase-start-time=no", "--force-window=yes"]
    if n is not None:
        moments = shown(doc)
        if not 1 <= n <= len(moments):
            msg = f"no moment {n} (1..{len(moments)})"
            raise IndexError(msg)
        name = moments[n - 1].get("file", name)
        first_frame = next((p["start_s"] for p in parts if p["file"] == name), first_frame)
        cmd.append(f"--start={max(first_frame, moments[n - 1]['t'] - LEAD_S):.3f}")
    return [*cmd, str(rec_dir / name)]


def open_moment(doc: Doc, rec_dir: Path, n: int | None, *, dry_run: bool) -> int:
    """Plays the recording in mpv at moment n (or prints the command when `dry_run`)."""
    cmd = open_command(doc, rec_dir, n)
    if dry_run:
        sys.stdout.write(shlex.join(cmd) + "\n")
        return 0
    return subprocess.call(cmd)
