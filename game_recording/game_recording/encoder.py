# Copyright (c) 2026 Krzysztof Rudnicki
"""The ffmpeg command line of a session recording.

External recorder, so the game's frame time is untouched: x11grab of the game
window, PulseAudio/PipeWire monitor audio, hardware encode. Godot's MovieWriter
is not an option: it forces fixed-step, non-realtime playback.

Timestamps: frames are stamped with the wall clock as ffmpeg reads them
(-use_wallclock_as_timestamps) and pulse stamps audio with it by default.
x11grab hands a frame over 1 to 2 frame periods after the screen had that
content (measured at 60 and 120 fps under Xvfb), so the video input is shifted
back by the middle of that range (GRAB_LATENCY_FRAMES): a stamp then lies within
half a frame of the moment its content was on screen. -copyts keeps
those absolute and -output_ts_offset -T0 moves them so the file's timeline
starts at T0, a unix time the launcher chose. That makes the offset between the
game's telemetry (unix-stamped by recording_sync) and the file exact, with no
guess about ffmpeg's start-up latency.
"""

from dataclasses import dataclass
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Collection

NVENC = "h264_nvenc"
X264 = "libx264"
NVENC_P7_MAX_PIXELS = 2560 * 1440
# Measured: x11grab frames are stamped 1..2 frame periods after their content.
GRAB_LATENCY_FRAMES = 1.5
DEFAULT_MONITOR = "@DEFAULT_MONITOR@"
# A silent source for tests only: stamped with the wall clock like pulse is.
LAVFI_AUDIO = "anullsrc=r=48000:cl=stereo"
LAVFI_STAMP = "asetpts='RTCTIME/(1000000*TB)'"


class NoEncoderError(Exception):
    """Neither NVENC nor libx264 can encode here."""


@dataclass(frozen=True)
class Spec:
    """What one recorder part needs to know."""

    window_id: int
    fps: int
    t0_unix: float
    out: str
    audio: str = "default"  # "default" = monitor of the default sink; "lavfi" = test silence; else a pulse source
    display: str = ":0"
    width: int = 0  # window size; an odd side is cropped to even (h264 yuv420 needs it)
    height: int = 0


def pick(usable: Collection[str]) -> str:
    """NVENC when it works (the RTX 3090 encodes without touching the game's frame time), else x264."""
    for name in (NVENC, X264):
        if name in usable:
            return name
    msg = "neither h264_nvenc nor libx264 is usable"
    raise NoEncoderError(msg)


def probe_usable() -> set[str]:
    """Encoders that really encode one frame here (listed is not the same as working)."""
    ok: set[str] = set()
    for name in (NVENC, X264):
        cmd = ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=size=256x256:rate=1", "-frames:v", "1"]
        cmd += ["-c:v", name, "-f", "null", "-"]
        done = subprocess.run(cmd, capture_output=True, check=False, timeout=20)
        if not done.returncode:
            ok.add(name)
    return ok


def nvenc_preset(width: int, height: int) -> str:
    """The NVENC preset: p7 (best quality) while it keeps real time on the RTX 3090.

    Measured 1.7x at 2560x1440, 2.4x at 1920x1200; above 1440p p7 only reaches 0.78x at 4K, p4 does 1.6x.
    """
    return "p7" if width * height <= NVENC_P7_MAX_PIXELS else "p4"


def _video_codec(name: str, width: int = 0, height: int = 0) -> list[str]:
    if name == NVENC:
        preset = nvenc_preset(width, height)
        return ["-c:v", NVENC, "-preset", preset, "-tune", "hq", "-rc", "vbr", "-cq", "17", "-b:v", "0", "-g", "60"]
    return ["-c:v", X264, "-crf", "16", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-g", "60"]


def _even_crop(spec: Spec) -> list[str]:
    if spec.width % 2 or spec.height % 2:
        return ["-vf", "crop=trunc(iw/2)*2:trunc(ih/2)*2"]
    return []


def _audio_input(audio: str) -> tuple[list[str], list[str]]:
    """(input args, output filter args) of the audio source."""
    if audio == "lavfi":
        return ["-f", "lavfi", "-i", LAVFI_AUDIO], ["-af", LAVFI_STAMP]
    source = DEFAULT_MONITOR if audio == "default" else audio
    return ["-thread_queue_size", "1024", "-f", "pulse", "-i", source], []


def command(spec: Spec, codec: str) -> list[str]:
    """The ffmpeg argv. SIGINT makes it finalize the file.

    -shortest ends it when x11grab dies (window unmapped, resized or gone), which the launcher
    takes as the cue for a new part.
    """
    audio_in, audio_filter = _audio_input(spec.audio)
    return [
        "ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin", "-y",
        "-thread_queue_size", "1024", "-use_wallclock_as_timestamps", "1",
        "-itsoffset", f"{-GRAB_LATENCY_FRAMES / spec.fps:.6f}", "-f", "x11grab", "-window_id", f"0x{spec.window_id:x}",
        "-framerate", str(spec.fps), "-draw_mouse", "0", "-i", spec.display,
        *audio_in,
        "-copyts", "-output_ts_offset", f"{-spec.t0_unix:.6f}",
        *_even_crop(spec),
        *_video_codec(codec, spec.width, spec.height),
        "-c:a", "flac", *audio_filter,
        "-shortest", "-f", "matroska", spec.out,
    ]  # fmt: skip
