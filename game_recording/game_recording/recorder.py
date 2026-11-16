# Copyright (c) 2026 Krzysztof Rudnicki
"""The recorder beside the game: gpu-screen-recorder, or ffmpeg x11grab as the fallback.

One part file per run of the recorder; every part sits on the same t0 timeline (the
unix time of the first part's time 0), see encoder.py (x11grab) and gsr.py.
"""

from dataclasses import dataclass, field
import json
import os
import signal
import subprocess
import sys
import time
from typing import TYPE_CHECKING

from game_recording import encoder, gsr, procs, window

if TYPE_CHECKING:
    from pathlib import Path

    from game_recording.options import RecorderOptions

WINDOW_WAIT_S = 30.0
RETURN_WAIT_S = 3600.0  # a window that went away may take a whole break to return
MAX_QUICK_DEATHS = 3  # ffmpeg dying right at start this many times in a row: give up
RECORDER_NICE = 10
STOP_GRACE_S = 20.0
SHORT_LIFE_S = 5.0  # a gsr part that ends sooner than this counts against gsr
X11GRAB_SETTLE_S = 1.0  # still running after this long = recording


def say(message: str) -> None:
    """One status line on stderr."""
    sys.stderr.write(f"record: {message}\n")
    sys.stderr.flush()


def stop_recorder(proc: subprocess.Popen[bytes], grace_s: float = STOP_GRACE_S) -> bool:
    """SIGINT so the recorder writes the trailer; kill only after the grace. True = it finalized by itself."""
    if proc.poll() is not None:
        return True
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=grace_s)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        return False
    return True


def part_file(session: str, number: int) -> str:
    """Part 1 is <session>.mkv; each restart (window came back) adds <session>.partN.mkv."""
    return f"{session}.mkv" if number == 1 else f"{session}.part{number}.mkv"


@dataclass
class GsrState:
    """What the recorder remembers about gpu-screen-recorder parts."""

    open_part: tuple[Path, float] | None = None  # (file, first-frame unix) of the running part
    pending: list[tuple[Path, float]] = field(default_factory=list)  # ended parts, aligned after the game
    first_frames: dict[str, float] = field(default_factory=dict)  # part file -> unix time of its first frame
    started: float = 0.0  # monotonic start of the running part
    short_lives: int = 0


class Recorder:
    """The recorder process, restarted when the game's window goes away and returns.

    The window capture ends when the window is unmapped (an i3 workspace switch), resized or
    replaced. Each run is a part file on the same t0 timeline; the time between
    parts is simply not in the video (events there are `in_gap`). `backend` is "gsr" or
    "x11grab"; a gsr that fails to start switches the rest of the session to x11grab.
    """

    def __init__(self, game: subprocess.Popen[bytes], paths: dict[str, Path], opts: RecorderOptions) -> None:
        """Watches `game`; writes into `paths` (dir, video, events, meta, log)."""
        self.game, self.paths, self.opts = game, paths, opts
        self.backend = opts.backend
        self.proc: subprocess.Popen[bytes] | None = None
        self.parts: list[str] = []
        self.t0 = 0.0
        self.quick_deaths = 0
        self.off = False
        self.win: window.Window | None = None  # the window the running part records
        self.gsr = GsrState()

    def _write_meta(self, codec: str, win: window.Window) -> None:
        meta = {
            "session": self.opts.session, "t0_unix": self.t0, "video": self.parts[0], "parts": self.parts,
            "feedback": str(self.opts.feedback / "feedback.jsonl"), "encoder": codec, "backend": self.backend,
            "first_frame_unix": self.gsr.first_frames, "audio": self.opts.audio, "fps": self.opts.fps,
            "window": {"id": win.id, "width": win.width, "height": win.height},
        }  # fmt: skip
        self.paths["meta"].write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")

    def _spec(self, win: window.Window, out: Path) -> encoder.Spec:
        return encoder.Spec(
            window_id=win.id, fps=self.opts.fps, t0_unix=self.t0, out=str(out),
            audio=self.opts.audio, display=os.environ["DISPLAY"], width=win.width, height=win.height,
        )  # fmt: skip

    def _start_gsr(self, win: window.Window, name: str, out: Path) -> bool:
        with self.paths["log"].open("ab") as log:
            started = gsr.start(self._spec(win, out), log, self.opts.nice)
        if started is None:
            say(f"gpu-screen-recorder failed to start, using x11grab; see {self.paths['log']}")
            self.backend = "x11grab"
            return False
        self.proc, first = started
        if not self.parts:
            self.t0 = first  # the timeline starts at the first frame, exactly (see gsr.py)
        self.parts.append(name)
        self.gsr.open_part = (out, first)
        self.gsr.first_frames[name] = first
        self.gsr.started = time.monotonic()
        self._write_meta("gsr-h264", win)
        say(f"recording {win.width}x{win.height} with gpu-screen-recorder -> {out}")
        self.quick_deaths = 0
        return True

    def _start_x11grab(self, win: window.Window, name: str, out: Path) -> None:
        codec = encoder.pick(self.opts.usable)
        if not self.parts:
            self.t0 = time.time()  # the files' timeline starts here, exactly (see encoder.py)
        spec = self._spec(win, out)
        self.parts.append(name)
        self._write_meta(codec, win)
        with self.paths["log"].open("ab") as log:
            cmd = procs.niced(self.opts.nice, encoder.command(spec, codec))
            self.proc = procs.spawn(cmd, log=log, detach=True)
        try:
            self.proc.wait(timeout=X11GRAB_SETTLE_S)
        except subprocess.TimeoutExpired:
            say(f"recording {win.width}x{win.height} with {codec} -> {out}")
            self.quick_deaths = 0
            return
        self.quick_deaths += 1
        self.parts.pop()
        self.proc = None
        say(f"ffmpeg died at start, see {self.paths['log']}")
        self.off = self.quick_deaths >= MAX_QUICK_DEATHS

    def _start_part(self, win: window.Window) -> None:
        name = part_file(self.opts.session, len(self.parts) + 1)
        out = self.paths["dir"] / name
        self.paths["dir"].mkdir(parents=True, exist_ok=True)
        self.win = win
        if self.backend == "gsr" and self._start_gsr(win, name, out):
            return
        self._start_x11grab(win, name, out)

    def close_part(self) -> None:
        """The running gsr part has ended. Aligning it is a remux (disk I/O), so it waits for the game's end."""
        if self.gsr.open_part is not None:
            self.gsr.pending.append(self.gsr.open_part)
            self.gsr.open_part = None

    def _align_pending(self) -> None:
        """Moves each ended gsr part onto the t0 timeline (stream copy). Trouble is only reported."""
        pending, self.gsr.pending = self.gsr.pending, []
        for video, first in pending:
            try:
                gsr.align(video, first_unix=first, t0=self.t0)
            except (subprocess.SubprocessError, OSError, ValueError) as err:
                say(f"could not align {video.name} to the timeline: {err}")

    def _count_short_life(self) -> None:
        """A gsr that keeps dying soon after it started is replaced by x11grab for the rest of the session."""
        if self.gsr.open_part is None:
            return
        young = time.monotonic() - self.gsr.started < SHORT_LIFE_S
        self.gsr.short_lives = self.gsr.short_lives + 1 if young else 0
        if self.gsr.short_lives >= MAX_QUICK_DEATHS:
            say("gpu-screen-recorder keeps stopping, using x11grab")
            self.backend = "x11grab"

    def _still_recording(self) -> bool:
        """True while the running part is fine; ends a gsr part whose window changed."""
        if self.proc is None or self.proc.poll() is not None:
            return False
        if self.gsr.open_part is None or window.largest(self.game.pid) == self.win:
            return True
        # x11grab dies with its window; gsr neither exits nor resumes after an unmap
        # (an i3 workspace switch), so its part is ended here and the next one waits.
        stop_recorder(self.proc)
        return False

    def step(self) -> bool:
        """One look at the recorder; True while a part is being recorded."""
        if self.off:
            return False
        if self._still_recording():
            return True
        first = not self.parts
        if self.proc is not None:
            say("recorder stopped (the window went away); waiting for it to come back")
            self.proc = None
            self._count_short_life()
            self.close_part()
        win = window.wait_stable(
            self.game.pid, WINDOW_WAIT_S if first else RETURN_WAIT_S, lambda: self.game.poll() is None
        )
        if win is None:
            if first:
                say("no game window found, not recording")
                self.off = True
            return False
        try:
            self._start_part(win)
        except (encoder.NoEncoderError, OSError) as err:
            say(f"not recording: {err}")
            self.off = True
        return self.proc is not None

    def stop(self) -> None:
        """Ends the running part (SIGINT, kill after the grace) and aligns the gsr parts."""
        if self.proc is not None and not stop_recorder(self.proc):
            say("the recorder ignored SIGINT and was killed; the mkv keeps what was written")
        self.close_part()
        self._align_pending()
