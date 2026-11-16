# Copyright (c) 2026 Krzysztof Rudnicki
"""After the game exits: events.json next to the video, chapters remuxed in (no re-encode)."""

import json
from pathlib import Path
import subprocess
from typing import TYPE_CHECKING, Any

from game_recording import gsr, timeline

if TYPE_CHECKING:
    from game_recording.config import MomentMap


def _ffprobe(*args: str) -> dict[str, Any]:
    cmd = ["ffprobe", "-v", "error", "-of", "json", *args]
    done = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=60)
    probed: dict[str, Any] = json.loads(done.stdout)
    return probed


TAIL_S = 5.0  # only the file's last seconds are scanned for its true end


def probe_span(video: Path) -> tuple[float, float]:
    """(first timestamp, duration) in seconds on the file's timeline.

    The end is the last packet's end, not the container's Duration (muxers differ on
    whether that counts from zero or from the first timestamp).
    """
    fmt = _ffprobe("-show_entries", "format=start_time,duration", str(video))["format"]
    start = float(fmt.get("start_time", 0))
    scan = ["-show_entries", "packet=pts_time,duration_time", "-of", "json"]
    if "duration" in fmt:  # a finalized file: jump near the end (cues) instead of reading it all
        scan = ["-read_intervals", f"{max(0.0, float(fmt['duration']) - TAIL_S)}%", *scan]
    packets = _ffprobe(*scan, str(video))["packets"]
    end = max(
        (float(p["pts_time"]) + float(p.get("duration_time", 0)) for p in packets if "pts_time" in p), default=start
    )
    return start, max(0.0, end - start)


def embed_chapters(video: Path, ffmetadata: Path) -> None:
    """Remux with chapters, streams copied, timestamps kept (-copyts) so t stays valid."""
    tmp = video.with_suffix(".chapters.mkv")
    cmd = ["ffmpeg", "-v", "error", "-y", "-copyts", "-i", str(video), "-f", "ffmetadata", "-i", str(ffmetadata)]
    cmd += ["-map", "0", "-map_metadata", "0", "-map_chapters", "1", "-c", "copy", "-f", "matroska", str(tmp)]
    subprocess.run(cmd, check=True, timeout=300)
    tmp.replace(video)


def _part_spans(folder: Path, meta: dict[str, Any]) -> list[dict[str, Any]]:
    """Each existing part file with its first timestamp and duration (gsr parts are aligned first)."""
    names = [n for n in meta.get("parts") or [meta["video"]] if (folder / n).is_file()]
    for name, first in (meta.get("first_frame_unix") or {}).items():  # gsr parts: a no-op once aligned
        if name in names:
            gsr.align(folder / name, first_unix=float(first), t0=float(meta["t0_unix"]))
    spans = []
    for name in names:
        start_s, duration_s = probe_span(folder / name)
        spans.append({"file": name, "start_s": start_s, "duration_s": duration_s})
    return spans


def _embed_all_chapters(folder: Path, doc: dict[str, Any], parts: list[dict[str, Any]]) -> None:
    """Remuxes each part that has moments inside it with its chapters."""
    ffmeta = folder / f"{doc['session']}.ffmeta"
    for part in parts:
        chapters = timeline.chapters_ffmetadata(doc["events"], part["duration_s"], part["start_s"], file=part["file"])
        if "[CHAPTER]" in chapters:
            ffmeta.write_text(chapters, encoding="utf-8")
            embed_chapters(folder / part["file"], ffmeta)
    ffmeta.unlink(missing_ok=True)


def finalize(meta_path: Path, moment_map: MomentMap) -> dict[str, Any]:
    """Builds <session>.events.json and each part's chapters from <session>.rec.json; returns the document."""
    meta_path = Path(meta_path)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    folder = meta_path.parent
    parts = _part_spans(folder, meta)
    entries = timeline.load_session(Path(meta["feedback"]), meta["session"])
    doc = timeline.build_events(
        entries, session=meta["session"], t0_unix=float(meta["t0_unix"]), parts=parts, moment_map=moment_map
    )
    doc["video"]["file"] = parts[0]["file"]
    doc["video"]["encoder"] = meta.get("encoder", "")
    _embed_all_chapters(folder, doc, parts)
    out = folder / f"{meta['session']}.events.json"
    out.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    return doc
