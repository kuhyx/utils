# Copyright (c) 2026 Krzysztof Rudnicki
"""Runs the game and, for a person's own dev play, an external recorder beside it.

The game is a child process; its window is found by pid; the recorder
(gpu-screen-recorder, else ffmpeg x11grab, with the audio monitor) starts once the
window has settled and gets SIGINT when the game exits, so the mkv is finalized.
Then finalize.py writes events.json + chapters.
Recording trouble never changes the game's exit code or stops the game.
"""

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import secrets
import signal
import subprocess
import threading
import time
from typing import TYPE_CHECKING

from game_recording import encoder, finalize, gsr, policy, procs, timeline
from game_recording.options import RecorderOptions, RunOptions
from game_recording.recorder import Recorder, say

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from types import FrameType

    from game_recording.config import Config

SESSION_ARG = "--session-id="
FEEDBACK_ARG = "--feedback-dir="
POLL_S = 0.5
# What finalize can fail with: files, JSON (NoSyncError is a ValueError), a missing key, ffmpeg.
# Recording trouble must not fail the play session.
FINALIZE_ERRORS = (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError)
DEFAULT_NICE = "10"


def session_of(command: Sequence[str]) -> str:
    """The session id the command already carries, "" when none."""
    return policy.arg_value(command, SESSION_ARG)


def with_session(command: Sequence[str], session: str) -> list[str]:
    """The command with `--session-id=` among the game's user args (an existing one wins)."""
    return _with_user_arg(command, SESSION_ARG, session)


def _with_user_arg(command: Sequence[str], prefix: str, value: str) -> list[str]:
    out = list(command)
    if policy.arg_value(out, prefix):
        return out
    if "--" not in out:
        out.append("--")
    return [*out, f"{prefix}{value}"]


def feedback_dir(command: Sequence[str], env: Mapping[str, str], config: Config) -> Path:
    """Where the game's telemetry goes: --feedback-dir=, else the binaries folder's feedback/."""
    forced = policy.arg_value(command, FEEDBACK_ARG)
    if forced:
        return Path(forced)
    binaries = env.get(config.binaries_var)
    if binaries:
        return Path(binaries) / "feedback"
    return Path(env.get("HOME", str(Path.home()))) / config.binaries_dir / "feedback"


def recording_paths(feedback: Path, session: str) -> dict[str, Path]:
    """Every file of one recording, by role."""
    rec = feedback / "recordings"
    return {
        "dir": rec,
        "video": rec / f"{session}.mkv",
        "events": rec / f"{session}.events.json",
        "meta": rec / f"{session}.rec.json",
        "log": rec / f"{session}.ffmpeg.log",
    }


def new_session() -> str:
    """A fresh session id: unix time plus four hex digits."""
    return f"{int(time.time())}-run-{secrets.token_hex(2)}"


def _forward_signals(game: subprocess.Popen[bytes]) -> None:
    """The launcher is a thin parent: kill/hangup go to the game; Ctrl-C already reaches it directly."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    def forward(number: int, _frame: FrameType | None) -> None:
        game.send_signal(number)

    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, forward)


def _stop_game(game: subprocess.Popen[bytes]) -> None:
    if game.poll() is None:
        game.send_signal(signal.SIGTERM)


def _finish(paths: dict[str, Path], config: Config) -> None:
    if not paths["meta"].exists():
        return
    try:
        doc = finalize.finalize(paths["meta"], config.moments)
        shown = sum(1 for e in doc["events"] if timeline.in_recording(e))
        parts = doc["video"]["parts"]
        gaps = f", {len(parts)} parts" if len(parts) > 1 else ""
        say(f"{paths['dir'] / doc['video']['file']} ({doc['video']['duration_s']:.0f} s, {shown} moments{gaps})")
    except FINALIZE_ERRORS as err:
        say(f"could not build the timeline: {err}")


def _nice(env: Mapping[str, str], config: Config) -> str:
    """The recorder's nice value; `<prefix>_RECORDER_NICE=0` for tests under a CPU cap."""
    return env.get(config.env_name("RECORDER_NICE"), DEFAULT_NICE)


def _play_unrecorded(command: Sequence[str], env: Mapping[str, str]) -> int:
    game = procs.spawn(command, env=env)
    _forward_signals(game)
    return game.wait()


def _watch(game: subprocess.Popen[bytes], recorder: Recorder, options: RunOptions) -> None:
    """Steps the recorder until the game exits."""
    timer_started = False
    while game.poll() is None:
        recording = recorder.step()
        if options.max_seconds > 0 and not timer_started and (recording or recorder.off):
            timer_started = True  # the test flag: stop the game N s after recording began
            threading.Timer(options.max_seconds, _stop_game, (game,)).start()
        time.sleep(POLL_S)


def _play_recorded(command: Sequence[str], env: Mapping[str, str], config: Config, options: RunOptions) -> int:
    session = session_of(command) or options.session or new_session()
    fb = feedback_dir(command, env, config)
    argv = _with_user_arg(with_session(command, session), FEEDBACK_ARG, str(fb))
    paths = recording_paths(fb, session)
    with ThreadPoolExecutor(max_workers=1) as pool:
        usable = pool.submit(encoder.probe_usable)  # NVENC init overlaps the game's start
        game = procs.spawn(argv, env=env)
        _forward_signals(game)
        opts = RecorderOptions(
            session=session,
            feedback=fb,
            fps=options.fps,
            audio=options.audio,
            nice=_nice(env, config),
            usable=frozenset(usable.result()),
            backend=gsr.pick_backend(env, options.audio, config, have_gsr=gsr.available()),
        )
        recorder = Recorder(game, paths, opts)
        _watch(game, recorder, options)
    code = game.wait()
    recorder.stop()
    _finish(paths, config)
    return code


def run(
    command: Sequence[str],
    config: Config,
    options: RunOptions | None = None,
    env: Mapping[str, str] | None = None,
) -> int:
    """Runs `command`; records it when policy allows. Returns the game's exit code."""
    options = options or RunOptions()
    env = os.environ if env is None else env
    decision = policy.decide(command, env, config, force=options.force)
    if not decision.record:
        say(f"off ({decision.reason})")
        return _play_unrecorded(command, env)
    return _play_recorded(command, env, config, options)
